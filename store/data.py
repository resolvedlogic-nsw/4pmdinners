# store/data.py
# Central data definition for all Lighthouse Church merchandise

COLOURS = ['Camel', 'Army', 'Ecru', 'Navy', 'Black', 'Grey Marle', 'Sage', 'White', 'Bone', 'Pistachio', 'Pink', 'Burgundy', 'Carolina Blue', 'Red']

COLOUR_HEX = {
    'Camel':        '#C19A6B',
    'Army':         '#4B5320',
    'Ecru':         '#F0E6CA',
    'Navy':         '#001F5B',
    'Black':        '#1a1a1a',
    'Grey Marle':   '#9E9E9E',
    'Sage':         '#8FAF8A',
    'White':        '#F5F5F5',
    'Bone':         '#E8DCC8',
    'Pistachio':    '#93C572',
    'Pink':         '#F4A7B9',
    'Burgundy':     '#800020',
    'Carolina Blue':'#56A0D3',
    'Red':          '#C0392B',
}

# slug -> { name, category, sizes, variants: { colour: { price, image } } }
PRODUCTS = {
    'mens-hoodies': {
        'name': "Men's Hoodies",
        'category': 'mens',
        'size_chart': 'mens-hoodies',
        'sizes': ['XS', 'S', 'M', 'L', 'XL', 'XXL', 'XXXL', '4XL', '5XL'],
        'variants': {
            'Camel':  {'price': 45, 'image': 'mh-camel.png'},
            'Army':   {'price': 45, 'image': 'mh-army.png'},
            'Ecru':   {'price': 45, 'image': 'mh-ecru.png'},
            'Navy':   {'price': 45, 'image': 'mh-navy.png'},
        },
    },
    'mens-tshirts': {
        'name': "Men's T-Shirts",
        'category': 'mens',
        'size_chart': 'mens-tshirts',
        'sizes': ['XS', 'S', 'M', 'L', 'XL', 'XXL', 'XXXL', '4XL', '5XL'],
        'variants': {
            'Ecru':  {'price': 20, 'image': 'mt-ecru.png'},
            'Navy':  {'price': 20, 'image': 'mt-navy.png'},
            'Black': {'price': 20, 'image': 'mt-black.png'},
            'Sage':  {'price': 20, 'image': 'mt-sage.png'},
            'White': {'price': 20, 'image': 'mt-white.png'},
        },
    },
    'mens-zipper-hoodies': {
        'name': "Men's Zipper Hoodies",
        'category': 'mens',
        'size_chart': 'mens-zipper-hoodies',
        'sizes': ['XS', 'S', 'M', 'L', 'XL', 'XXL', 'XXXL'],
        'variants': {
            'Navy':      {'price': 40, 'image': 'mz-navy.png'},
            'Black':     {'price': 40, 'image': 'mz-black.png'},
            'Grey Marle':{'price': 40, 'image': 'mz-grey.png'},
        },
    },
    'womens-hoodies': {
        'name': "Women's Hoodies",
        'category': 'womens',
        'size_chart': 'womens-hoodies',
        'sizes': ['XS', 'S', 'M', 'L', 'XL', 'XXL', 'XXXL'],
        'variants': {
            'Ecru':      {'price': 45, 'image': 'wh-ecru.png'},
            'Black':     {'price': 45, 'image': 'wh-black.png'},
            'Grey Marle':{'price': 45, 'image': 'wh-grey.png'},
            'Bone':      {'price': 45, 'image': 'wh-bone.png'},
            'Pistachio': {'price': 45, 'image': 'wh-pistachio.png'},
        },
    },
    'womens-slim-tshirts': {
        'name': "Women's Slim Fit T-Shirts",
        'category': 'womens',
        'size_chart': 'womens-slim-tshirts',
        'sizes': ['XS', 'S', 'M', 'L', 'XL', 'XXL', 'XXXL'],
        'variants': {
            'Navy':      {'price': 20, 'image': 'ws-navy.png'},
            'Black':     {'price': 20, 'image': 'ws-black.png'},
            'Grey Marle':{'price': 20, 'image': 'ws-grey.png'},
            'Sage':      {'price': 20, 'image': 'ws-sage.png'},
            'White':     {'price': 20, 'image': 'ws-white.png'},
        },
    },
    'womens-maple-tshirts': {
        'name': "Women's Maple T-Shirts",
        'category': 'womens',
        'size_chart': 'womens-maple-tshirts',
        'sizes': ['XS', 'S', 'M', 'L', 'XL', 'XXL', 'XXXL'],
        'variants': {
            'Pink':         {'price': 20, 'image': 'wm-pink.png'},
            'Burgundy':     {'price': 20, 'image': 'wm-burgundy.png'},
            'Carolina Blue':{'price': 20, 'image': 'wm-carolina.png'},
        },
    },
    'kids-hoodies': {
        'name': "Kids and Teens Hoodies",
        'category': 'kids',
        'size_chart': 'kids-hoodies',
        'sizes': ['2', '4', '6', '8', '10', '12', '14', '16',],
        'variants': {
            'Navy':      {'price': 30, 'image': 'kh-navy.png'},
            'Grey Marle':{'price': 30, 'image': 'kh-grey.png'},
            'Pink':      {'price': 30, 'image': 'kh-pink.png'},
            'Red':       {'price': 30, 'image': 'kh-red.png'},
        },
    },
    'kids-tshirts': {
        'name': "Kids and Teens T-Shirts",
        'category': 'kids',
        'size_chart': 'kids-tshirts',
        'sizes': ['2', '4', '6', '8', '10', '12', '14', '16',],
        'variants': {
            'Navy':    {'price': 20, 'image': 'kt-navy.png'},
            'Black':   {'price': 20, 'image': 'kt-black.png'},
            'Sage':    {'price': 20, 'image': 'kt-sage.png'},
            'Pink':    {'price': 20, 'image': 'kt-pink.png'},
            'Burgundy':{'price': 20, 'image': 'kt-burgundy.png'},
        },
    },
}

CATEGORIES = [
    ('mens',   "Men's"),
    ('womens', "Women's"),
    ('kids',   "Kids"),
]

SIZE_CHARTS = {
    'mens-hoodies': {
        'name': "Men's Hoodies",
        'sizes': ['XS', 'S', 'M', 'L', 'XL', 'XXL', 'XXXL', '4XL', '5XL'],
        'measurements': {
            'Body Width (cm)':  [49, 52, 55, 58, 61, 64, 67, 70, 73],
            'Body Length (cm)': [65, 71, 74, 77, 79.5, 82, 84.5, 86, 87.5],
        },
    },
    'mens-tshirts': {
        'name': "Men's T-Shirts",
        'sizes': ['XS', 'S', 'M', 'L', 'XL', 'XXL', 'XXXL', '4XL', '5XL'],
        'measurements': {
            'Body Width (cm)':  [43, 47, 52, 56.5, 61, 64, 68, 75, 80],
            'Body Length (cm)': [68, 71, 75, 78.5, 82, 83.5, 85, 87, 89],
        },
    },
    'mens-zipper-hoodies': {
        'name': "Men's Zipper Hoodies",
        'sizes': ['XS', 'S', 'M', 'L', 'XL', 'XXL', 'XXXL'],
        'measurements': {
            'Body Width (cm)':  [49, 52, 55, 58, 61, 64, 67],
            'Body Length (cm)': [66, 72, 74.5, 77, 79.5, 82, 84.5],
        },
    },
    'womens-hoodies': {
        'name': "Women's Hoodies",
        'sizes': ['XS', 'S', 'M', 'L', 'XL', 'XXL', 'XXXL'],
        'measurements': {
            'Body Width (cm)':  [47, 49.5, 52, 54.5, 57, 59.5, 66.5],
            'Body Length (cm)': [62, 65, 68, 72, 75, 77, 79],
        },
    },
    'womens-maple-tshirts': {
        'name': "Women's Maple T-Shirts",
        'sizes': ['XS', 'S', 'M', 'L', 'XL', 'XXL', 'XXXL'],
        'measurements': {
            'Body Width (cm)':  [45.5, 48, 50.5, 53, 55.5, 58, 60.5],
            'Body Length (cm)': [63.5, 64.5, 65.5, 66.5, 67.5, 68.5, 69.5],
        },
    },
    'womens-slim-tshirts': {
        'name': "Women's Slim Fit T-Shirts",
        'sizes': ['XS', 'S', 'M', 'L', 'XL', 'XXL', 'XXXL'],
        'measurements': {
            'Body Width (cm)':  [43, 45.5, 48, 50.5, 53, 55.5, 58],
            'Body Length (cm)': [69.5, 71, 73.5, 75.5, 77.5, 79.5, 81.5],
        },
    },
    'kids-hoodies': {
        'name': "Kids and Teens Hoodies",
        'sizes': ['2', '4', '6', '8', '10', '12'],
        'measurements': {
            'Body Width (cm)':  [33, 36, 39, 42, 45, 48],
            'Body Length (cm)': [41, 45, 50, 54, 58, 61],
        },
    },
    'kids-tshirts': {
        'name': "Kids and Teens T-Shirts",
        'sizes': ['2', '4', '6', '8', '10', '12', '14', '16'],
        'measurements': {
            'Body Width (cm)':  [31, 34, 37, 39.5, 42, 44.5, 47, 49.5],
            'Body Length (cm)': [42, 46, 50, 54, 58, 62, 66, 70],
        },
    },
}
