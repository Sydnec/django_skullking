var socket = new ReconnectingWebSocket('ws://localhost:8001/ws/room_updates/');
socket.onmessage = function (event) {
	var data = JSON.parse(event.data);
	// dataExample = {message: "update_rooms", data: {code: "H668Q6", usernames: ["Sydnec", "Player1"], message: "join"}}
	if (data.message === 'update_rooms') {
		var roomData = data.data;
		updateRoomList(roomData);
	}

	function createRoomLi(roomData) {
		// Créer l'élément li
		var li = document.createElement('li');
		li.classList.add('room-line-content', roomData.code);
		var div = document.createElement('div');
		div.classList.add('player-list-line', roomData.code);
		// Ajouter les noms d'utilisateur à l'intérieur de la div
		roomData.usernames.forEach(function (username) {
			var span = document.createElement('span');
			span.classList.add('username-line');
			span.textContent = username;
			div.appendChild(span);
		});
		// Créer le formulaire
		var form = document.createElement('form');
		form.action = '/room/' + roomData.code + '/';
		form.method = 'post';

		// Ajouter le token CSRF
		var csrfTokenInput = document.createElement('input');
		csrfTokenInput.type = 'hidden';
		csrfTokenInput.name = 'csrfmiddlewaretoken';
		csrfTokenInput.value = '{{ csrf_token }}';
		form.appendChild(csrfTokenInput);

		// Ajouter l'input pour l'ID de la salle
		var roomIdInput = document.createElement('input');
		roomIdInput.type = 'hidden';
		roomIdInput.name = 'room_id';
		roomIdInput.value = roomData.code;
		form.appendChild(roomIdInput);

		// Créer le bouton pour rejoindre la salle
		var joinButton = document.createElement('button');
		joinButton.type = 'submit';
		joinButton.textContent = 'Join room';

		// Ajouter le bouton au formulaire
		form.appendChild(joinButton);

		// Ajouter la div et le formulaire à l'élément li
		li.appendChild(div);
		li.appendChild(form);
		return li;
	}
	function updateRoomList(roomData) {
		switch (roomData.message) {
			case 'leave':
				document
					.querySelectorAll(
						`.player-list-line.${roomData.code} .username-line`
					)
					.forEach(function (element) {
						if (
							roomData.usernames.includes(element.textContent) ===
							false
						) {
							element.remove();
						}
					});
				break;
			case 'join':
				document
					.querySelectorAll(
						`.player-list-line.${roomData.code} .username-line`
					)
					.forEach(function (element) {
						element.remove();
					});
				roomData.usernames.forEach(function (username) {
					var spanElement = document.createElement('span');
					spanElement.className = 'username-line';
					spanElement.textContent = username;
					var playerList = document.querySelector(
						`.player-list-line.${roomData.code}`
					);
					playerList.appendChild(spanElement);
				});
				break;
			case 'create':
				var roomList = document.querySelector('.room-list ul');
				roomList.appendChild(createRoomLi(roomData));
				break;
			case 'delete':
				var roomLine = document.querySelector(
					`.room-line-content.${roomData.code}`
				);
				roomLine.remove();
				break;
			default:
				break;
		}
	}
};
