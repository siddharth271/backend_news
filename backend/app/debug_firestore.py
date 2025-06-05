# debug_firestore.py - Create this file to test Firestore connection
import os
from google.cloud import firestore
from datetime import datetime

# Point to the downloaded service account key file
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "../credentials/firebase-adminsdk.json"


def test_firestore_connection():
    try:
        print("Testing Firestore connection...")
        db = firestore.Client()

        # Test 1: Try to connect and get database info
        print("✓ Firestore client created successfully")

        # Test 2: Check if collection exists and has data
        collection_name = "news_summaries"
        docs = list(db.collection(collection_name).stream())
        print(f"✓ Found {len(docs)} documents in '{collection_name}' collection")

        if docs:
            print("Sample documents:")
            for i, doc in enumerate(docs[:3]):  # Show first 3 docs
                print(f"  Doc {i + 1}: {doc.id} -> {doc.to_dict()}")
        else:
            print("Collection is empty - let's add a test document")

            # Test 3: Add a test document
            test_data = {
                "title": "Test News Item",
                "summary": "This is a test summary",
                "author": ["Test Author"],
                "published_date": datetime.now().isoformat(),
                "source": "test-source",
                "url": "https://example.com/test"
            }

            doc_ref = db.collection(collection_name).add(test_data)
            print(f"✓ Added test document with ID: {doc_ref[1].id}")

            # Test 4: Try to read it back
            docs = list(db.collection(collection_name).stream())
            print(f"✓ Now found {len(docs)} documents in collection")

    except Exception as e:
        print(f"❌ Error: {e}")
        print(f"Error type: {type(e)}")

        # Check if credentials file exists
        cred_path = "../credentials/firebase-adminsdk.json"
        if os.path.exists(cred_path):
            print(f"✓ Credentials file exists at: {cred_path}")
        else:
            print(f"❌ Credentials file NOT found at: {cred_path}")
            print(f"Current working directory: {os.getcwd()}")


if __name__ == "__main__":
    test_firestore_connection()