from myapp.views.home import home
from myapp.views.game import display, startgame, bet
from myapp.views.logout import logout
from myapp.views.room import newroom, joinroom, leaveroom, room_redirect
from myapp.views.register import RegisterView

from django.urls import path, re_path
# from django.contrib import admin
from django.contrib.auth import views as auth_views

# app_name = 'myapp'
urlpatterns = [
    path('', home, name='home'),
    # path('admin/', admin.site.urls),
    path('accounts/login/', auth_views.LoginView.as_view(template_name='myapp/login.html'), name='login'),
    path('login/', auth_views.LoginView.as_view(template_name='myapp/login.html'), name='login'),
    path('logout/', logout, name='logout'),
    path('register/', RegisterView.as_view(), name='register'),
    path('room/', newroom, name='newroom'),
    path('room_redirect/', room_redirect, name='room_redirect'),
    path('bet/', bet, name='bet'),
    path('room/<room_id>', display, name='room'),
    re_path(r'^room/(?P<room_id>[a-zA-Z0-9]{6})/$', display),  
    path('leave/<room_id>', leaveroom, name='leave'),
    re_path(r'^leave/(?P<room_id>[a-zA-Z0-9]{6})/$', leaveroom),  
    path('start/<room_id>', startgame, name='start'),
    re_path(r'^start/(?P<room_id>[a-zA-Z0-9]{6})/$', startgame),  
]
