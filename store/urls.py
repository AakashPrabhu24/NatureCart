# store/urls.py

from django.urls import path
from django.contrib.auth import views as auth_views
from . import views


urlpatterns = [
    path('', views.home, name='home'),
    path('product/<int:product_id>/', views.product_detail, name='product_detail'),
    # Other URLs...
]
# store/urls.py
urlpatterns += [
    path('products/', views.products, name='products'),
    path('category/<int:category_id>/', views.category_products, name='category_products'),
]

urlpatterns += [
    path('register/', views.register, name='register'),
    path('login/', auth_views.LoginView.as_view(template_name='store/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='home'), name='logout'),
]

urlpatterns += [
   path('remove-from-cart/<int:item_id>/', views.remove_from_cart, name='remove_from_cart'),
   path('payment-handler/', views.payment_handler, name='payment_handler'),
   path('cart/', views.cart_view, name='cart_view'),
   path('add-to-cart/<int:product_id>/', views.add_to_cart, name='add_to_cart'),

]


urlpatterns += [
    path('checkout/', views.checkout, name='checkout'),
]

urlpatterns += [
    # ... other paths ...
    path('buy-multiple-ingredients/', views.buy_multiple_ingredients, name='buy_multiple_ingredients'),


]
urlpatterns += [
    # ... other paths ...
    path('add_to_cart_multiple_ingredients/', views.add_to_cart_multiple_ingredients, name='add_to_cart_multiple_ingredients'),
    
]
urlpatterns += [
path('remove-ingredient/<int:ingredient_id>/', views.remove_ingredient_from_cart, name='remove_ingredient_from_cart'),

]
urlpatterns += [
path('search/', views.search_results, name='search_results'),


]