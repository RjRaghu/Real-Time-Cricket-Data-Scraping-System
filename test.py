from pymongo import MongoClient

# Connect to local MongoDB (default port 27017)
client = MongoClient("mongodb://localhost:27017")

# Choose the database (must match what you typed in the shell, or create a new one)
db = client["myCricketDB"]

# Choose/create a collection
matches_collection = db["matches_data"]

# Insert a test doc
doc = {"hello": "world"}
result = matches_collection.insert_one(doc)
print("Inserted _id:", result.inserted_id)
