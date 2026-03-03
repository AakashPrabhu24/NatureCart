from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse
from .models import Product, Category, Cart, CartItem, Ingredient
from .forms import UserRegisterForm
import razorpay
from django.conf import settings
import hmac
import hashlib


def home(request):
    products = Product.objects.all()
    return render(request, 'store/home.html', {'products': products})


def product_detail(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    return render(request, 'store/product_detail.html', {'product': product})


def products(request):
    categories = Category.objects.all()
    products = Product.objects.all()
    return render(request, 'store/products.html', {
        'categories': categories,
        'products': products
    })


def category_products(request, category_id):
    categories = Category.objects.all()
    products = Product.objects.filter(category_id=category_id)
    selected_category = get_object_or_404(Category, id=category_id)
    return render(request, 'store/products.html', {
        'categories': categories,
        'products': products,
        'selected_category': selected_category
    })


def register(request):
    if request.method == 'POST':
        form = UserRegisterForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('login')
    else:
        form = UserRegisterForm()
    return render(request, 'store/register.html', {'form': form})


def get_user_cart(user):
    cart, created = Cart.objects.get_or_create(user=user)
    return cart


@login_required
def add_to_cart(request, product_id):
    if request.method == 'POST':
        quantity = int(request.POST.get('quantity', 1))
        product = get_object_or_404(Product, id=product_id)
        cart = get_user_cart(request.user)

        cart_item, created = CartItem.objects.get_or_create(cart=cart, product=product)
        if not created:
            cart_item.quantity += quantity
        else:
            cart_item.quantity = quantity
        cart_item.save()

        return redirect('cart_view')

    return redirect('product_detail', product_id=product_id)


@login_required
def add_to_cart_multiple_ingredients(request):
    if request.method == 'POST':
        cart = get_user_cart(request.user)

        idx = 0
        while True:
            ingredient_id = request.POST.get(f'ingredients[{idx}][id]')
            quantity = request.POST.get(f'ingredients[{idx}][quantity]')
            if ingredient_id is None:
                break
            quantity = int(quantity)

            ingredient = get_object_or_404(Ingredient, pk=ingredient_id)
            # Add your logic here to add ingredient and quantity to the cart
            # For now, we'll store ingredients in session until you set up proper models
            cart_session = request.session.get('ingredient_cart', {})
            cart_session[ingredient_id] = cart_session.get(ingredient_id, 0) + quantity
            request.session['ingredient_cart'] = cart_session

            idx += 1

        return redirect('cart_view')

    return redirect('products')


@login_required
def cart_view(request):
    cart = get_user_cart(request.user)
    items = cart.items.select_related('product').all()
    cart_items = []

    for item in items:
        line_total = item.product.price * item.quantity
        cart_items.append({
            'product': item.product,
            'quantity': item.quantity,
            'line_total': line_total,
            'id': item.id
        })

    # Fetch ingredients from session cart
    cart_ingredients = []
    ingredients_total = 0
    ingredient_cart = request.session.get('ingredient_cart', {})
    
    for ingredient_id, quantity in ingredient_cart.items():
        ingredient = get_object_or_404(Ingredient, pk=ingredient_id)
        line_total = ingredient.price * quantity
        ingredients_total += line_total
        cart_ingredients.append({
            'ingredient': ingredient,
            'quantity': quantity,
            'line_total': line_total,
        })

    # Calculate totals
    products_total = sum(ci['line_total'] for ci in cart_items)
    total_amount = products_total + ingredients_total

    return render(request, 'store/cart.html', {
        'cart_items': cart_items,
        'cart_ingredients': cart_ingredients,
        'products_total': products_total,
        'ingredients_total': ingredients_total,
        'total_amount': total_amount
    })


@login_required
def remove_from_cart(request, item_id):
    cart_item = get_object_or_404(CartItem, id=item_id, cart__user=request.user)
    if request.method == 'POST':
        cart_item.delete()
    return redirect('cart_view')


from decimal import Decimal

@login_required
def checkout(request):
    cart = get_user_cart(request.user)
    
    # Calculate product totals
    products_total = sum(item.product.price * item.quantity for item in cart.items.all())
    
    # Calculate ingredients totals from session
    ingredients_total = Decimal('0.00')
    ingredient_cart = request.session.get('ingredient_cart', {})
    ingredients_list = []
    
    for ingredient_id, quantity in ingredient_cart.items():
        ingredient = get_object_or_404(Ingredient, pk=ingredient_id)
        ingredient_total = ingredient.price * quantity
        ingredients_total += ingredient_total
        ingredients_list.append({
            'ingredient': ingredient,
            'quantity': quantity,
            'total': ingredient_total
        })
    
    # Calculate totals using Decimal for consistency
    subtotal = products_total + ingredients_total
    tax = subtotal * Decimal('0.18')  # 18% GST as Decimal
    shipping = Decimal('50.00') if subtotal > 0 else Decimal('0.00')  # ₹50 shipping
    total_amount = subtotal + tax + shipping
    
    # Amount in paise for Razorpay (convert to int)
    amount_paise = int(total_amount * 100)

    client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
    payment = client.order.create({'amount': amount_paise, 'currency': 'INR', 'payment_capture': '1'})

    context = {
        'payment': payment,
        'key_id': settings.RAZORPAY_KEY_ID,
        'amount': total_amount,
        'amount_paise': amount_paise,
        'subtotal': subtotal,
        'products_total': products_total,
        'ingredients_total': ingredients_total,
        'tax': tax,
        'shipping': shipping,
        'cart': cart,
        'ingredient_cart': ingredient_cart,
        'ingredients_list': ingredients_list
    }
    return render(request, 'store/checkout.html', context)


@csrf_exempt
def payment_handler(request):
    if request.method == "POST":
        razorpay_order_id = request.POST.get('razorpay_order_id')
        razorpay_payment_id = request.POST.get('razorpay_payment_id')
        razorpay_signature = request.POST.get('razorpay_signature')

        generated_signature = hmac.new(
            key=bytes(settings.RAZORPAY_KEY_SECRET, 'utf-8'),
            msg=bytes(razorpay_order_id + "|" + razorpay_payment_id, 'utf-8'),
            digestmod=hashlib.sha256
        ).hexdigest()

        if generated_signature == razorpay_signature:
            # Payment successful - update order status in DB, clear cart, etc.
            return HttpResponse("Payment Successful")
        else:
            return HttpResponse("Payment Verification Failed", status=400)
    else:
        return HttpResponse(status=405)


def buy_ingredient(request, ingredient_id):
    ingredient = get_object_or_404(Ingredient, id=ingredient_id)
    return render(request, 'store/buy_ingredient.html', {'ingredient': ingredient})


def buy_multiple_ingredients(request):
    if request.method == 'POST':
        # For demonstration, get all posted ingredient IDs and quantities
        ingredients = []
        idx = 0
        while True:
            ingredient_id = request.POST.get(f'ingredients[{idx}][id]')
            quantity = request.POST.get(f'ingredients[{idx}][quantity]')
            if not ingredient_id:
                break
            ingredients.append({'id': ingredient_id, 'quantity': quantity})
            idx += 1
        # You now have a list of all selected ingredients and their quantities
        # Render a summary page, process payment, etc.
        return render(request, 'store/buy_multiple.html', {'selected_ingredients': ingredients})
    return render(request, 'store/buy_multiple.html')


@login_required
def remove_ingredient_from_cart(request, ingredient_id):
    if request.method == 'POST':
        # Get ingredient cart from session
        ingredient_cart = request.session.get('ingredient_cart', {})
        
        # Remove the ingredient if it exists
        if str(ingredient_id) in ingredient_cart:
            del ingredient_cart[str(ingredient_id)]
            request.session['ingredient_cart'] = ingredient_cart
            request.session.modified = True  # Ensure session is saved
    
    return redirect('cart_view')
from django.db.models import Q, Case, When, IntegerField
from django.contrib.postgres.search import SearchVector, SearchQuery, SearchRank
import re

def search_results(request):
    query = request.GET.get('q', '').strip()
    products = []
    ingredients = []
    
    if query and len(query) >= 2:  # Minimum 2 characters
        # Clean and prepare search terms
        search_terms = re.findall(r'\b\w+\b', query.lower())
        
        if search_terms:
            # Build Q objects for products with relevance scoring
            product_queries = Q()
            for term in search_terms:
                product_queries |= (
                    Q(name__icontains=term) |
                    Q(recipe__icontains=term) |
                    Q(category__name__icontains=term)
                )
            
            # Search products with relevance ranking
            products = Product.objects.filter(product_queries).annotate(
                relevance=Case(
                    # Exact name match gets highest score
                    When(name__iexact=query, then=100),
                    # Name starts with query gets high score
                    When(name__istartswith=query, then=90),
                    # Name contains query gets medium score
                    When(name__icontains=query, then=70),
                    # Category match gets lower score
                    When(category__name__icontains=query, then=50),
                    # Recipe match gets lowest score
                    When(recipe__icontains=query, then=30),
                    default=0,
                    output_field=IntegerField()
                )
            ).filter(relevance__gt=0).order_by('-relevance', 'name').distinct()
            
            # Build Q objects for ingredients
            ingredient_queries = Q()
            for term in search_terms:
                ingredient_queries |= Q(name__icontains=term)
            
            # Search ingredients with relevance ranking
            ingredients = Ingredient.objects.filter(ingredient_queries).annotate(
                relevance=Case(
                    When(name__iexact=query, then=100),
                    When(name__istartswith=query, then=90),
                    When(name__icontains=query, then=70),
                    default=0,
                    output_field=IntegerField()
                )
            ).filter(relevance__gt=0).order_by('-relevance', 'name').distinct()
    
    # Limit results for better performance
    products = products[:20]  # Top 20 products
    ingredients = ingredients[:10]  # Top 10 ingredients
    
    context = {
        'query': query,
        'products': products,
        'ingredients': ingredients,
        'products_count': products.count() if products else 0,
        'ingredients_count': ingredients.count() if ingredients else 0,
        'min_search_length': 2,
    }
    
    return render(request, 'store/search_results.html', context)
