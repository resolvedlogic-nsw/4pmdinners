# Lighthouse Merch Store — Integration Guide
# Adding the `store` app to your existing mylighthouse project

## 1. Copy the app

Copy the `store/` folder into your project root (next to your other apps):

    mylighthouse/
    ├── store/               ← copy here
    ├── members/             (existing app)
    ├── mylighthouse/        (project settings)
    └── manage.py

## 2. Install the Square SDK (if not already installed)

    pip install squareup

On PythonAnywhere, run this in a Bash console:

    pip3.10 install --user squareup

## 3. Register the app in settings.py

In `mylighthouse/settings.py`, add `'store'` to INSTALLED_APPS:

    INSTALLED_APPS = [
        ...
        'store',
    ]

## 4. Add URL routing in urls.py

In `mylighthouse/urls.py`, add the store URLs under `/store/`:

    from django.urls import path, include

    urlpatterns = [
        ...
        path('store/', include('store.urls')),
    ]

## 5. Add product images

Create the directory:

    store/static/store/img/

Drop all product images in there. Filenames must match exactly:

    Men's Hoodies:          mh-camel.png  mh-army.png  mh-ecru.png  mh-navy.png
    Men's T-Shirts:         mt-ecru.png   mt-navy.png  mt-black.png mt-sage.png  mt-white.png
    Men's Zipper Hoodies:   mz-navy.png   mz-black.png mz-grey.png
    Women's Hoodies:        wh-ecru.png   wh-black.png wh-grey.png  wh-bone.png  wh-pistachio.png
    Women's Slim T-Shirts:  ws-navy.png   ws-black.png ws-grey.png  ws-sage.png  ws-white.png
    Women's Maple T-Shirts: wm-pink.png   wm-burgundy.png  wm-carolina.png
    Kid's Hoodies:          kh-navy.png   kh-grey.png  kh-pink.png  kh-red.png
    Kid's T-Shirts:         kt-navy.png   kt-black.png kt-sage.png  kt-pink.png  kt-burgundy.png

Run collectstatic after adding images:

    python manage.py collectstatic

## 6. Check your .env / environment variables

The store reads these (already in your .env):

    SQUARE_ACCESS_TOKEN=your_token
    SQUARE_LOCATION_ID=your_location_id
    SQUARE_ENVIRONMENT=production

Make sure your settings.py loads these via python-dotenv or os.environ.
The store reads them at runtime with `os.environ.get(...)`.

## 7. Square payment link redirect URL

The checkout creates a Square payment link with a redirect back to:

    https://my.lighthouse.net.au/store/success/

Square will redirect there after payment. If your domain differs, update
`views.py` → `checkout()` → the `redirect_url` in `create_payment_link`.

For cancellation, Square shows a "Cancel" link — to redirect cancelled
payments back to your site, set the cancel URL in your Square Dashboard
under: Payments → Payment Links → Settings.

## 8. Session configuration

The cart uses Django sessions. Confirm sessions are enabled in settings.py:

    INSTALLED_APPS = [..., 'django.contrib.sessions', ...]
    MIDDLEWARE = [..., 'django.contrib.sessions.middleware.SessionMiddleware', ...]
    SESSION_ENGINE = 'django.contrib.sessions.backends.db'  # default, fine

Run migrations if you haven't:

    python manage.py migrate

## 9. Link from your homepage

In your main index template, replace the JotForm link with:

    <a href="/store/">
      <img src="/static/merch.jpg" alt="Merch">
    </a>

Or whatever wraps your existing merch.jpg tile.

## 10. Reload the web app on PythonAnywhere

After pushing all files, go to the Web tab and click Reload.

---

## File structure summary

    store/
    ├── __init__.py
    ├── data.py                  ← all product/size/colour data
    ├── views.py                 ← all views + Square integration
    ├── urls.py                  ← URL patterns (app_name='store')
    ├── templatetags/
    │   ├── __init__.py
    │   └── store_tags.py        ← getitem filter for templates
    ├── templates/store/
    │   ├── base.html            ← Lighthouse-themed base
    │   ├── product_list.html    ← shop home, grouped by category
    │   ├── product_detail.html  ← colour/size selector, add to cart
    │   ├── cart.html            ← cart review
    │   ├── checkout.html        ← name/email form → Square redirect
    │   ├── success.html         ← post-payment confirmation
    │   ├── cancel.html          ← payment cancelled
    │   └── size_chart.html      ← full size guide
    └── static/store/
        └── img/                 ← drop product images here

## Adding/changing products later

All product data lives in `store/data.py`. To add a product:
1. Add an entry to the `PRODUCTS` dict with a unique slug
2. Add its size chart to `SIZE_CHARTS`
3. Add its images to `store/static/store/img/`
4. Run `collectstatic` and reload

No database, no migrations needed — everything is data-driven from data.py.
