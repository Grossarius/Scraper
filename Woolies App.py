import pandas as pd
import json
import openai
import os
from dotenv import load_dotenv
import re
import inflect
from collections import defaultdict
from decimal import Decimal
from typing import Dict, List, Tuple, Union

# Setup
load_dotenv()
GPT_MODEL = "gpt-3.5-turbo"
openai.api_key = os.getenv("OPENAI_API_KEY")
p = inflect.engine()
# Items that has one of these ingredients will be removed from the result
bad_list = [

    "Artificial flavor",
    "Artificial flavour",
    "Natural flavor",
    "Natural flavour",
    "Aspartame",
    "BHT",
    "Calcium disodium EDTA",
    "Color",
    "Colour",
    "Carrageenan",
    "Corn starch",
    "Corn syrup",
    "Dextrose",
    "Dough conditioners",
    "Enriched flour",
    "Bleached flour",
    "Food color",
    "Maltodextrin",
    "Monoglycerides",
    "Monosodium glutamate",
    "Diglyceride",
    "Natural flavor",
    "Natural flavors",
    "Polysorbate",
    "Potassium sorbate",
    "Sodium erythorbate",
    "Sodium nitrate",
    "Sodium nitrite",
    "Sodium phosphate",
    "Soy protein isolate",
    "Splenda",
    "Sugar",
    "Syrup",
    "Sweetener",
    "Skim milk",
    "Low fat",
    "Reduced fat",
    "Xylitol",
]

# ChatGPT setup to return JSON formatted data
def json_gpt(input: str) -> Dict:
    completion = openai.ChatCompletion.create(
        model=GPT_MODEL,
        messages=[
            {"role": "system", "content": "Output only valid JSON"},
            {"role": "user", "content": input},
        ],
        temperature=0.5,
    )
    text = completion.choices[0].message.content
    print(text)
    parsed = json.loads(text)
    return parsed

# ChatGPT to get ingredients from recipes
def get_recipe_ingredients(recipe: str) -> List[str]:
    QUERIES_INPUT = f"""
    Get all the ingredients in the recipe. 
    This is the recipe: {recipe}
    Only include ingredients that are in the recipe, don't include the measurements.
    Format: {{"Ingredients": ["ingredient_1", "ingredient_2",...]}}
    """

    similar_products = json_gpt(QUERIES_INPUT)["Ingredients"]
    return similar_products

# ChatGPT to categorize data into their general categories that match the Woolies app
def categorize_ingredients(ingredients: List[str]) -> Dict[str, List[str]]:
    # Give ChatGPT related subcategories of the general categories -> better chance of finding the right category
    category_dict = {
        "bakery": ["bakery", "bread", "pastries"],
        "dairy-eggs-fridge": ["dairy-eggs-fridge", "milk", "cheese", "yogurt", "cream", "dips", "ready meals", "international food", "vegan"],
        "drinks": ["drinks", "juices", "soda", "water", "tea", "coffee", "energy drinks"],
        "freezer": ["freezer", "frozen meals", "ice cream", "frozen vegetables", "frozen fruit"],
        "fruit-veg": ["fruit-veg", "fruits", "vegetables", "salads", "organic", "fresh herbs"],
        "health-wellness health-foods": ["health-wellness", "vitamins", "superfoods", "protein bars", "health-foods", "health foods", "dried fruit, nuts, seeds"],
        "lunch-box": ["lunch-box", "sandwiches", "snack packs", "fruit cups"],
        "pantry": ["pantry", "canned goods", "breakfast and spreads", "spices", "condiments", "pasta, rice, grains", "cooking sauces", "oil and vinegar", "international foods"],
        "poultry-meat-seafood": ["poultry-meat-seafood", "poultry", "meat", "seafood"]
    }
    # Put them all into a list for ChatGPT and then re-categorize them later
    category_list = [item for sublist in category_dict.values() for item in sublist]
    # Hard coding so ChatGPT doesn't have to process some ingredients -> Save money
    known_category = {
        "bakery": ["bakery", "bread", "pastries"],
        "dairy-eggs-fridge": ["parmigiano reggiano", "milk", "cheese", "yogurt", "cream", "dips", "butter","egg"],
        "drinks": ["drinks", "juices", "soda", "water", "tea", "coffee", "energy drinks"],
        "freezer": ["freezer", "frozen meals", "ice cream", "frozen vegetables", "frozen fruit"],
        "fruit-veg": ["scallion", "chopped onion", "white onion", "garlic cloves", "basil", "lime", "lemon","ginger", "chilli"],
        "health-wellness health-foods": ["health-wellness", "vitamins", "superfoods", "protein bars", "health-foods", "health foods", "dried fruit, nuts, seeds"],
        "lunch-box": [],
        "pantry": ["fish sauce", "flour", "self-raising flour"],
        "poultry-meat-seafood": ["poultry", "meat", "seafood"]
    }
    known_product = {}
    for product in ingredients:
        product2 = p.singular_noun(product.lower()) or product.lower()   
        for k, v in known_category.items():
            if product2 in v:
                known_product[k] = known_product.get(k, []) + [product]
                print(product)
                ingredients.remove(product)
                break

    # ChatGPT to help categorize items
    QUERIES_INPUT = f"""
    Group the items into their respective categories. Use ONLY the provided categories and items to create the desired grouping.

    Categories: {category_list}
    Items: {ingredients}

    Skip empty lists.
    Make sure to group all the items.

    Format: 
    "category_1": ["item_1", "item_2", ...],
    "category_2": ["item_1", "item_2", ...],
    """

    ingredients = json_gpt(QUERIES_INPUT)
    print("Output from GPT: ", ingredients)
    # Combine the known categories and the ones from ChatGPT
    ingredients = {key: known_product.get(key, []) + ingredients.get(key, []) for key in set(known_product) | set(ingredients)}
    # Merge the subcategories into the general categories
    categorized_items = {}
    for key, value in ingredients.items():
        for category, keywords in category_dict.items():
            # Check if any keyword in the category is present in the item
            if key in keywords:
                categorized_items[category] = categorized_items.get(category, []) + value
                break
    # Filter out ones with empty list
    categorized_items = {key: value for key, value in categorized_items.items() if value}
    # Remove duplicate
    for key, values in categorized_items.items():
        categorized_items[key] = list(set(values))
    return categorized_items

# Find all the good products of an item (ex: Item: Soba Noodles -> Products: "Obento Soba Noodles", "Redrock Soba Noodles", "Hakubaku Soba Noodles")")    
def find_product(product: str, df, k: str, filter_ingredient = True, bad_list: List[str] = bad_list) -> pd.DataFrame:
    # Hard code: remove an ingredient from the bad list and add them back later (ex: Syrup is bad but Maple Syrup isn't)
    add_list = []
    if "maple syrup" in product:
        add_list.append("Syrup")
        bad_list.remove("Syrup")
    # Hard code: renaming/removing/replacing words from the product's name
    if "scallion" in product:
        product = "spring onion"
    if "ketchup" in product:
        product = "tomato sauce"
    if "ground" in product:
        product = product.replace("ground", "mince")
    if ("raising" in product and "flour" in product) or "self-raising" in product:
        product = "raising flour"
    
    all_replace = ["parmesan", "cheddar", "basil", "oregano", "pepper flakes", "spaghetti"]
    for i in all_replace:
        if i in product:
            product = i

    words_to_remove = ["dry", "chopped", "shred", "shredded", "diced", "sliced", "grated", "cubed", "julienne", "pureed", "mashed", "leaves", "crushed", "sliced", "whole", "boneless"]
    for word in words_to_remove:
        if word in product:
            product = product.replace(word, "")

    # Default: make the product singular. So the items below will be pluralized
    product = p.singular_noun(product.lower()) or product.lower()
    product = product.strip()
    
    words_to_pluralize = ["noodle", "egg"]
    exit_loop = False
    for word in words_to_pluralize:
        if exit_loop:
            break
        for w in product.split():
            if word == w:
                product = p.plural(product)
                exit_loop = True
                break

    # Split the product name into words to look up in the database (ex: Some brands say Noodles Soba instead of Soba Noodles)
    product_split = product.split()

    # Filter out rows that do not contain the product name
    selected_rows = df.copy()  # Create a copy of the original dataframe
    for keyword in product_split:
        selected_rows = selected_rows[selected_rows['Product Name'].str.contains(fr'\b{re.escape(keyword)}\b', case=False)]
    # Hard code
    # Filter out rows with no ingredients for certain categories only
    if k != 'fruit-veg' and k != 'poultry-meat-seafood':
        selected_rows = selected_rows[~selected_rows['Ingredients'].isna()]    
    
    # Select only rows that are within a department or similar criteria
    if product == "honey":
        selected_rows = selected_rows[selected_rows["Aisle"].str.lower() == "honey"]
    if product == "egg":
        selected_rows = selected_rows[selected_rows["Aisle"].str.lower() == "eggs"]
    if product == "ginger":
        selected_rows = selected_rows[selected_rows["Department"].str.lower() != "drink"]
    if product == "butter":
        selected_rows = selected_rows[selected_rows["Sap Category Name"].str.lower() == "dairy - butter & margarine"]
    if "spaghetti" in product:
        selected_rows = selected_rows[selected_rows["Sap Sub Category Name"].str.lower() == "pasta"]
    if any(word in product for word in ["parmesan", "cheddar", "mozzarella", "cheese"]):
        selected_rows = selected_rows[selected_rows["Department"].str.lower() == "dairy"]

    print("Len of selected rows (before filtering): ", len(selected_rows))

    # Get the 'Product Name' and 'Ingredients' columns as Series
    product_names = selected_rows['Product Name']
    ingredients_series = selected_rows['Ingredients']
    cup_prices = selected_rows['Cup Price']
    price = selected_rows['Price']
    stockcode = selected_rows['Stockcode']
    image = selected_rows['Medium Image File']
    cup = selected_rows['Cup Measure']

    clean_products_df = pd.DataFrame(columns=['Product Name', 'Ingredients', 'Cup Price', 'Price', 'Stockcode', "Image"])
    
    # Filter out the bad products and add the good ones to the clean_products_df
    for product_name, ingredients, cup_price, price, stockcode, image, cup in zip(product_names, ingredients_series, cup_prices, price, stockcode, image, cup):
        clean = True
        # For categories like fruit-veg or poultry-meat-seafood, the ingredients list is empty -> if isinstance
        # Split the string at commas that are not between parentheses
        # Filter out items with bad ingredients
        if filter_ingredient:
            if isinstance(ingredients, str):
                ingredients_list = re.split(r',\s*(?![^()]*\))', ingredients)
                # Iterate over each ingredient in the list
                for ingredient in ingredients_list:
                    # Check if the ingredient is in the bad_list
                    for bad_item in bad_list:
                        # Normalize bad_list item to lowercase and split it into individual words
                        bad_item_lower = bad_item.lower()
                        bad_words = re.findall(r'\b\w+\b', bad_item_lower)
                        
                        # Check if all the words from bad_list are present in the ingredient
                        all_words_present = all(word in ingredient.lower() for word in bad_words)
                        
                        if all_words_present:
                            clean = False
            else:
                ingredients_list = []
        else:
            ingredients_list = []
        # Ingredients shouldn't be more than a certain amount
        gum = 0
        oil = 0
        emulsifier = 0
        # Count the occurrences of specific ingredients
        gum = sum(ingredient.lower().count("gum") for ingredient in ingredients_list)
        oil = sum(ingredient.lower().count("oil") for ingredient in ingredients_list)
        emulsifier = sum(ingredient.lower().count("emulsifier") for ingredient in ingredients_list)

        if gum > 2 or oil > 2 or emulsifier > 2:
            clean = False

        # If the product is clean, add it to the list
        if clean:
            clean_products_df = pd.concat([clean_products_df, pd.DataFrame({
                'Product Name': [product_name],
                'Ingredients': [ingredients],
                'Cup Price': [cup_price],
                "Price": [price],
                "Stockcode": [stockcode],
                "Image": [image],
                "Cup": [cup]
            })])
    
    clean_products_df_sorted = clean_products_df.sort_values(by='Cup Price')
    if not clean_products_df_sorted.empty:
        print("Clean product found")
    # Add back the ingredients removed from the bad list
    for item in add_list:
        bad_list.append(item)
    return clean_products_df_sorted

# The main function that return all the good products, a grocery list, and a list of items that have no good products
def get_all_product(data: str, top = 5, bad_list: List[str] = bad_list) -> Tuple[Dict[str, List[Dict[str, any]]], List[Dict[str, any]], Dict[str, List[str]]]:
    all_none = {}
    all_res = defaultdict(list)

    ingredients = get_recipe_ingredients(data)
    categorized_items = categorize_ingredients(ingredients)

    # Load data and find product then add them to a json called all_res
    for k, v in categorized_items.items():
        # Load files
        # Because there are 2 files for pantry items
        file_path2 = None
        if k == "pantry":
            file_path = f"Data\Woolies Extracted\Woolies {k} 1 info.xlsx"
            file_path2 = f"Data\Woolies Extracted\Woolies {k} 2 info.xlsx"
        else:
            file_path = f"Data\Woolies Extracted\Woolies {k} info.xlsx"
        df = pd.read_excel(file_path)
        if file_path2:
            df2 = pd.read_excel(file_path2)
            df = pd.concat([df, df2], ignore_index=True)
        # Find product 
        for product in v:
            original_product = product
            print("Product: ", product)
            print("Category: ", k)
            # Skip unnecessary ingredients
            all_skip = ["water", "sugar", "salt"]
            skip = False
            for item in all_skip:
                if item in product:
                    skip = True
                    break
            if skip:
                continue
            clean_products_df_sorted = find_product(product, df, k, bad_list = bad_list)
            # Find similar products (ex: Spring onion -> green onion) if not found
            if clean_products_df_sorted.empty:
                similar_products = []
                for product in similar_products:
                    # If the product is not found, try to find the singular/plural version of the product
                    clean_products_df_sorted = find_product(product, df, k, bad_list = bad_list)
                    if not clean_products_df_sorted.empty:
                        break
                    print("Current alternative product: ", product)
            
            # GET THE TOP 5 CHEAPEST UNIT PRICE PRODUCTS
            for index, row in clean_products_df_sorted.head(top).iterrows():
                product_name = row['Product Name']
                ingredients = row['Ingredients']
                cup_price = row['Cup Price']
                price = row['Price']
                stockcode = row['Stockcode']
                image = row['Image']
                cup = row['Cup']
                
                all_res[product].append({
                    'product_name': product_name,
                    'ingredients': ingredients,
                    'cup_price': cup_price,
                    'price': price,
                    'stockcode': "https://www.woolworths.com.au/shop/productdetails/{}".format(stockcode),
                    'image': image,
                    'cup': cup
                })

            if clean_products_df_sorted.empty:
                all_none[k] = all_none.get(k, []) + [original_product]
        buy_list = []
        for k, v in all_res.items():
            lowest_price = float('inf')
            lowest_price_product = None
            # Iterate over the product list to find the product with the lowest price
            for product in v:
                price = product['price']
                if price < lowest_price:
                    lowest_price = price
                    lowest_price_product = product
            buy_list.append(lowest_price_product)
    return all_res, buy_list, all_none
    
# Get the bad products that are not found (optional)
def get_bad_product(all_none):
    still_none = []
    all_res_2 = defaultdict(list)
    for k, v in all_none.items():
        file_path2 = None
        if k == "pantry":
            file_path = "Data\Woolies Extracted\Woolies {} 1 info.xlsx".format(k)
            file_path2 = "Data\Woolies Extracted\Woolies {} 2 info.xlsx".format(k)
        else:
            file_path = "Data\Woolies Extracted\Woolies {} info.xlsx".format(k)
        df = pd.read_excel(file_path)
        if file_path2:
            df2 = pd.read_excel(file_path2)
            df = pd.concat([df, df2], ignore_index=True)
        for product in v:
            print(product)
            original_product = product
            clean_products_df_sorted = find_product(product, df, k, filter_ingredient=False, bad_list = bad_list)
            # GET THE TOP 5 CHEAPEST UNIT PRICE PRODUCTS
            for index, row in clean_products_df_sorted.head(5).iterrows():
                product_name = row['Product Name']
                ingredients = row['Ingredients']
                cup_price = row['Cup Price']
                price = row['Price']
                stockcode = row['Stockcode']
                image = row['Image']
                cup = row['Cup']
                
                all_res_2[product].append({
                    'product_name': product_name,
                    'ingredients': ingredients,
                    'cup_price': cup_price,
                    'price': price,
                    'stockcode': "https://www.woolworths.com.au/shop/productdetails/{}".format(stockcode),
                    'image': image,
                    'cup': cup
                })
            if clean_products_df_sorted.empty:
                still_none.append(original_product)
            print("------------------")
recipe = """
5 tbsp oil
2 eggs lightly beaten
3 tbsp cornflour/cornstarch
10 tbsp plain/all-purpose flour
2 tsp paprika
3 chicken breast fillets chopped into bite-size chunks
"""
all_res, buy_list, all_none = get_all_product(data = recipe, top = 5, bad_list = bad_list)
all_res_bad = get_bad_product(all_none)
print(buy_list)
print(len(buy_list))
print(all_none)