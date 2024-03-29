# myapp/views/game.py

from django.http import JsonResponse
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import render, redirect
from django.db.models import Max, Case, When
from myapp.models import *
from myapp.views.room import joinroom
from myapp.views.error import error
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from celery import shared_task
import random
import json
import time


@login_required
def display(request, room_id):
    room_id = room_id.upper()
    if room_id:
        user = request.user
        try:
            room = Room.objects.get(code=room_id) 
        except Room.DoesNotExist:
            return error(request, "Room doesn't exist")
        if room.rounds.count() <= 0: # La partie n'a pas encore commencé
            # Essayer de rejoindre la room (la gestion de s'il est présent se passe dans joinroom)
            if joinroom(request=request, room=room) == -1:
                return error(request, "Room is full")

            players = room.players.all()  
            usernames = [player.user.username for player in players]
            is_owner = room.owner == user
            return render(request, 'myapp/room.html', {'room_id': room_id, 'usernames': usernames, 'is_owner': is_owner})
        else: # La partie à commencer, soit t'en fait parti, soit retour home
            if room.players.filter(user=user).exists():
                return game_data(request, room)
            else:
                return error(request, "Game has already start")
    else:
        return error(request, "No room code found")

@login_required
def game_data(request, room):
    user = request.user
    players = room.players.all()
    current_round = room.rounds.all().latest('value')
    current_player = Player.objects.get(user=user, rooms=room)
    user_index = next((i for i, player in enumerate(players) if player == current_player), None)
    if user_index is not None:
        ordered_players = list(players[user_index + 1:]) + list(players[:user_index])
    players_cards_number = {}
    player_bets = {}

    try:
        player_bets[current_player] = Bet.objects.get(round=current_round, player=current_player)
    except Bet.DoesNotExist:
        player_bets[current_player] = None

    for player in ordered_players:
        try:
            players_cards_number[player] = CardAssociation.objects.filter(hand=Hand.objects.get(player=player), trick__isnull=True).count()
        except Bet.DoesNotExist:
            players_cards_number[player] = 0
        try:
            bet = Bet.objects.get(round=current_round, player=player)
            player_bets[player] = bet
        except Bet.DoesNotExist:
            player_bets[player] = None

    hand_cards = CardAssociation.objects.filter(round=current_round, hand=Hand.objects.get(player=current_player), trick__isnull=True)
    try:
        trick = Trick.objects.get(round=current_round)
        phase = 2
        trick_cards = CardAssociation.objects.filter(round=current_round, trick=trick)
    except Trick.DoesNotExist:
        phase = 1
        trick_cards = None

    # Ordonner les cartes
    trick_cards_ordered = None
    if trick_cards is not None:
        cases = [When(hand__player=player, then=index) for index, player in enumerate(getOrderedPlayers(current_round))]
        trick_cards_ordered = trick_cards.annotate(
            player_order=Case(*cases, default=len(ordered_players), output_field=models.IntegerField())
        ).order_by('player_order')
    
    data = {
        'room_id': room.code,
        'player_bets': player_bets,
        'round_number': current_round.value,
        'hand_cards': hand_cards,
        'trick_cards': trick_cards_ordered,
        'players_cards_number':players_cards_number,
    }
    if phase == 1:
        return render(request, 'myapp/bet.html', data)
    elif phase == 2:
        return render(request, 'myapp/table.html', data)

def next_round(room):
    # Création du round
    round_count = room.rounds.all().latest('value').value if room.rounds.exists() else 0
    new_round = Round.objects.create(room=room, value=round_count+1)
    room.rounds.add(new_round)
    # Distribution des cartes
    distribute_cards(room)
    # return game_data(request, room)

def distribute_cards(room):
    current_round = room.rounds.all().latest('value')
    cards_per_player = current_round.value + 9
    players = room.players.all()
    deck = CardAssociation.objects.filter(round=current_round)
    
    # Mélanger les cartes
    shuffled_cards = list(deck)
    random.shuffle(shuffled_cards)

    # Distribuer les cartes
    for player in players:
        hand = Hand.objects.filter(player=player).first()
        for i in range(cards_per_player):
            card_association = shuffled_cards.pop()
            card_association.hand = hand
            card_association.save()

def game_action(request):
    if request.method == 'POST':
        data = json.loads(request.body.decode('utf-8'))
        room_id = data.get('room_id')
        room = Room.objects.get(code=room_id)
        action = data.get('action')
        if action == "play":
            return play_card(request, room, data)
        elif action == "bet":
            return bet(request, room, data)
        elif action == "start":
            return startgame(request, room)

def startgame(request, room):
    if 1 < room.players.count() < 8:
        next_round(room)
        # Envoi de l'update sur websocket
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            'room_updates',
            {
                'type': 'update_rooms',
                'data': 'start'
            }
        )
    return game_data(request, room)

@shared_task
def game_phase(room):
    current_round = room.rounds.all().latest('value')
    if Trick.objects.filter(round=current_round).exists() == False:
        Trick.objects.create(round=current_round)

@shared_task
def bet_phase(room):
    next_round(room)

def play_card(request, room, data):
    user = request.user
    current_player = Player.objects.get(user=user, rooms=room)
    current_round = room.rounds.all().latest('value')
    current_trick = Trick.objects.get(round=current_round)
    # Vérifier tour de jeu
    if isYourTurn(current_player, current_trick):
        card_name = data.get('card_name')
        card_association = CardAssociation.objects.get(round=current_round, card=Card.objects.get(name=card_name))
        card_association.trick = current_trick
        card_association.save()
    # Passer au tour suivant si tout le monde a joué
    if CardAssociation.objects.filter(trick=current_trick).count() == room.players.count():
        current_trick.player = defineTrickWinner(request, current_trick)
        current_trick.save()
        bet_phase(room)
    return game_data(request, room)

def getOrderedPlayers(round):
    round_number = round.value
    players = round.room.players.all()
    if round_number == 1:
        first_player = Player.objects.get(user=round.room.owner, rooms=round.room)
    else:
        last_round = Round.objects.get(room=round.room, value=round_number-1)
        first_player = Trick.objects.get(round=last_round).player
    # Récupère l'ordre de jeu
    print(first_player)
    user_index = next((i for i, player in enumerate(players) if player == first_player), None)
    return [first_player] + list(players[user_index + 1:]) + list(players[:user_index])

def defineTrickWinner(request, trick):
    max_card = None
    ordered_players = getOrderedPlayers(trick.round)
    print(ordered_players)
    # Cartes spéciales
    pirates = CardAssociation.objects.filter(trick=trick, card__type="pirate") 
    sirens = CardAssociation.objects.filter(trick=trick, card__type="siren") 
    skullking = CardAssociation.objects.filter(trick=trick, card__type="skullking")
    if skullking.exists():
        print("skullking")
        if sirens.exists():
            print("siren")
            # Récupère la première sirene jouée
            sirens_players = [siren.hand.player for siren in sirens]
            for player in ordered_players:
                if player in sirens_players:
                    max_card = sirens.get(hand__player=player)
                    break
        else:
            max_card = skullking.first()
    elif pirates.exists():
        print("pirate")
        # Récupère le premier pirate joué
        pirates = [pirate.hand.player for pirate in pirates]
        for player in ordered_players:
            if player in sirens_players:
                max_card = sirens.get(hand__player=player)
                break
    else:
        print("no special card")
        # Aucune carte spéciale maitresse jouée
        colors = ["black", "green", "purple", "yellow"]
        for player in ordered_players:
            asked_color = CardAssociation.objects.get(hand__player=player, trick=trick).card.type
            if asked_color in colors:
                break
        print(asked_color)
        if asked_color in ["green", "purple", "yellow"]:
            # Récupère la meilleur carte à la couleur demandé
            max_value = CardAssociation.objects.filter(trick=trick, card__type=asked_color).aggregate(Max('card__value'))['card__value__max']
            print(max_value)
            max_card = CardAssociation.objects.get(trick=trick, card__type=asked_color, card__value=max_value) 
        # S'il y a des atouts, change la carte maitresse par le meilleur atout
        trumps = CardAssociation.objects.filter(trick=trick, card__type="black")
        if trumps.exists():
            max_value = trumps.aggregate(Max('card__value'))['card__value__max']
            max_card = CardAssociation.objects.get(trick=trick, card__type=asked_color, card__value=max_value) 
    # Si personne n'est vainqueur, alors le premier joueur remporte le pli
    if max_card is None:
        max_card = CardAssociation.objects.get(hand__player=ordered_players[0], trick=trick)
    return max_card.hand.player

def isYourTurn(current_player, trick):
    # Vérifier que le joueur n'a pas encore joué
    if CardAssociation.objects.filter(trick=trick, hand__player=current_player).exists(): 
        print("Déjà joué")
        return False

    # Si personne n'a encore joué ce tour
    if CardAssociation.objects.filter(trick=trick).exists() == False:
        round_number = trick.round.value
        if round_number == 1:
            return trick.round.room.owner == current_player.user
        else:
            last_round = Round.objects.get(room=trick.round.room, value=round_number-1)
            last_trick = Trick.objects.get(round=last_round)
            return last_trick.player == current_player
    else:
        ordered_players = getOrderedPlayers(trick.round)
        index_player = next((i for i, player in enumerate(ordered_players) if player == current_player), None)
        print(index_player)
        for player in ordered_players:
            print(player.user.username)
        print(ordered_players[index_player - 1].user.username)
        return CardAssociation.objects.filter(trick=trick, hand__player=ordered_players[index_player - 1]).exists()
    return True

def bet(request, room, data):
    user = request.user
    current_round = room.rounds.all().latest('value')
    bet_value = data.get('bet_value')
    current_player = Player.objects.get(user=user, rooms=room)

    bet = Bet.objects.filter(round=current_round, player=current_player)
    if bet.count() == 0:
        bet = Bet.objects.create(round=current_round, player=current_player)
    else:
        bet = bet.first()
    bet.value = bet_value
    bet.save()
    if Bet.objects.filter(round=current_round).count() == room.players.all().count():
        game_phase(room)
    return game_data(request, room)