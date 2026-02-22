#!/usr/bin/env python3
"""Verification script for Firebase Firestore persistence configuration."""

import sys
import os
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load environment variables from .env file
load_dotenv()

try:
    import firebase_admin
    from firebase_admin import credentials, firestore
except ImportError:
    print("Error: firebase-admin is not installed.")
    print("Install it with: pip install firebase-admin")
    sys.exit(1)


def verify_firebase():
    """Verify Firebase Firestore configuration and connectivity."""
    print("Firebase Firestore Verification")
    print("=" * 60)
    print("\nThis script verifies your Firebase Firestore configuration.")
    print("Make sure you have:")
    print("  1. Created a Firebase project at https://console.firebase.google.com/")
    print("  2. Created a Firestore database (if not, the script will guide you)")
    print("  3. Generated a service account JSON key")
    print("  4. Added FIREBASE_PROJECT_ID and FIREBASE_CREDENTIALS_PATH to your .env file")
    print("\nNote: The script cannot create the database automatically.")
    print("      You'll need to create it via Firebase Console if it doesn't exist.")
    print("=" * 60)
    
    # Get configuration from environment
    project_id = os.getenv("FIREBASE_PROJECT_ID")
    credentials_path = os.getenv("FIREBASE_CREDENTIALS_PATH")
    
    if not project_id:
        print("\n✗ Error: FIREBASE_PROJECT_ID environment variable is required")
        print("\nTo set up Firebase:")
        print("1. Go to https://console.firebase.google.com/")
        print("2. Create a new project or select existing project")
        print("3. Get your Firebase Project ID:")
        print("   - Go to Project Settings (gear icon)")
        print("   - Your Project ID is shown at the top (e.g., 'qmsf-e541d')")
        print("   - Or check the URL: https://console.firebase.google.com/project/YOUR-PROJECT-ID")
        print("4. Enable Firestore Database:")
        print("   - In Firebase Console, click 'Firestore Database' in the left sidebar")
        print("   - Click 'Create database'")
        print("   - Choose 'Start in test mode' (or production mode)")
        print("   - Select a location and click 'Enable'")
        print("   - OR enable via API: https://console.cloud.google.com/apis/library/firestore.googleapis.com")
        print("5. Get Service Account credentials:")
        print("   - Go to Project Settings > Service Accounts")
        print("   - Click 'Generate New Private Key' to download service account JSON")
        print("6. Add to your .env file:")
        print("   FIREBASE_PROJECT_ID=your-firebase-project-id")
        print("   FIREBASE_CREDENTIALS_PATH=/path/to/firebase-service-account.json")
        print("\n   Or export as environment variables:")
        print("   export FIREBASE_PROJECT_ID=your-firebase-project-id")
        print("   export FIREBASE_CREDENTIALS_PATH=/path/to/firebase-service-account.json")
        return 1
    
    if not credentials_path:
        print("\n✗ Error: FIREBASE_CREDENTIALS_PATH environment variable is required")
        print("\nAdd to your .env file:")
        print("   FIREBASE_CREDENTIALS_PATH=/path/to/firebase-service-account.json")
        print("\n   Or export as environment variable:")
        print("   export FIREBASE_CREDENTIALS_PATH=/path/to/firebase-service-account.json")
        return 1
    
    # Check if credentials file exists
    if not os.path.exists(credentials_path):
        print(f"\n✗ Error: Credentials file not found: {credentials_path}")
        return 1
    
    try:
        # Initialize Firebase Admin SDK
        print(f"\n1. Initializing Firebase Admin SDK...")
        print(f"   Project ID: {project_id}")
        print(f"   Credentials: {credentials_path}")
        
        cred = credentials.Certificate(credentials_path)
        app = firebase_admin.initialize_app(cred, {
            'projectId': project_id,
        })
        print("   ✓ Firebase initialized successfully")
        
        # Get Firestore client (optionally a named database and collection prefix)
        database_id = os.getenv("FIRESTORE_DATABASE_ID") or None
        collection_prefix = (os.getenv("PERSISTENCE_COLLECTION_PREFIX") or "").strip()
        if database_id and database_id != "(default)":
            print(f"   Database ID: {database_id}")
        if collection_prefix:
            print(f"   Collection prefix: {collection_prefix}")
        print("\n2. Connecting to Firestore...")
        try:
            if database_id and database_id != "(default)":
                db = firestore.client(database_id=database_id)
            else:
                db = firestore.client()
            print("   ✓ Connected to Firestore")
        except Exception as e:
            error_msg = str(e)
            if "does not exist" in error_msg or "404" in error_msg:
                print(f"   ✗ Error: {e}")
                print("\n⚠ Firestore database does not exist for your project.")
                print("\nTo create the Firestore database:")
                print("1. Go to Firebase Console:")
                print("   https://console.firebase.google.com/project/" + project_id)
                print("2. Click 'Firestore Database' in the left sidebar")
                print("3. Click 'Create database'")
                print("4. Choose 'Start in test mode' (or production mode with your security rules)")
                print("5. Select a location (choose closest to you, e.g., us-central1)")
                print("6. Click 'Enable'")
                print("\n   OR create via Google Cloud Console:")
                print(f"   https://console.cloud.google.com/datastore/setup?project={project_id}")
                print("\n   Wait a few minutes for the database to be created, then run this script again.")
                return 1
            else:
                raise
        
        # Verify collections exist (create test documents if needed)
        print("\n3. Verifying collections...")
        collections = ['trades', 'ownership', 'external_sales']
        
        for collection_name in collections:
            try:
                # Try to read from collection (will create it if it doesn't exist)
                full_name = f"{collection_prefix}{collection_name}"
                collection_ref = db.collection(full_name)
                # Create a test document to ensure collection exists
                test_doc_ref = collection_ref.document('_setup_test')
                test_doc_ref.set({
                    'created_at': firestore.SERVER_TIMESTAMP,
                    'setup_date': datetime.now().isoformat(),
                })
                # Delete test document
                test_doc_ref.delete()
                print(f"   ✓ Collection '{full_name}' verified")
            except Exception as e:
                error_msg = str(e)
                print(f"   ✗ Error verifying '{full_name}': {e}")
                
                # Check if it's a permissions (403) error
                if "403" in error_msg or "Missing or insufficient permissions" in error_msg or "Permission denied" in error_msg:
                    print("\n   Permission denied (403). Common causes:")
                    print("   - IAM can take 1–2 minutes to propagate after setup. Wait and run this script again.")
                    print("   - Service account needs 'Cloud Datastore Owner' or 'Cloud Datastore User' in IAM.")
                    print(f"   - Check: https://console.cloud.google.com/iam-admin/iam?project={project_id}")
                    return 1
                
                # Check if database doesn't exist
                if "does not exist" in error_msg or "404" in error_msg:
                    print("\n⚠ Firestore database does not exist for your project.")
                    print("\nTo create the Firestore database:")
                    print("1. Go to Firebase Console:")
                    print("   https://console.firebase.google.com/project/" + project_id)
                    print("2. Click 'Firestore Database' in the left sidebar")
                    print("3. Click 'Create database'")
                    print("4. Choose 'Start in test mode' (or production mode with your security rules)")
                    print("5. Select a location (choose closest to you, e.g., us-central1)")
                    print("6. Click 'Enable'")
                    print("\n   OR create via Google Cloud Console:")
                    print(f"   https://console.cloud.google.com/datastore/setup?project={project_id}")
                    print("\n   Wait a few minutes for the database to be created, then run this script again.")
                    return 1
                
                # Check if it's a Firestore API not enabled error
                if "SERVICE_DISABLED" in error_msg or "API has not been used" in error_msg or "it is disabled" in error_msg:
                    print("\n⚠ Firestore API is not enabled for your project.")
                    print("\nTo enable Firestore API:")
                    print("1. Go to Firebase Console:")
                    print("   https://console.firebase.google.com/project/" + project_id)
                    print("2. Click 'Firestore Database' in the left sidebar")
                    print("3. Click 'Create database'")
                    print("4. Choose 'Start in test mode' (or production mode)")
                    print("5. Select a location and click 'Enable'")
                    print("\n   OR enable via Google Cloud Console:")
                    print(f"   https://console.cloud.google.com/apis/library/firestore.googleapis.com?project={project_id}")
                    print("\n   Click 'Enable' and wait a few minutes for changes to propagate.")
                    print("\n   Then run this script again.")
                
                return 1
        
        # Test read/write operations
        print("\n4. Testing read/write operations...")
        test_collection = db.collection(f"{collection_prefix}_setup_test")
        test_doc = test_collection.document('test')
        test_doc.set({
            'message': 'Firebase setup test',
            'timestamp': datetime.now().isoformat(),
        })
        test_data = test_doc.get()
        if test_data.exists:
            print("   ✓ Write operation successful")
        else:
            print("   ✗ Write operation failed")
            return 1
        
        test_doc.delete()
        print("   ✓ Read/delete operations successful")
        
        print("\n" + "=" * 60)
        print("✓ Firebase Firestore verification completed successfully!")
        print("\nYour Firebase configuration is correct and ready to use.")
        print("\nYou can now enable persistence by setting:")
        print("  PERSISTENCE_ENABLED=true")
        print("\nOr it will auto-enable if Firebase credentials are configured.")
        return 0
        
    except Exception as e:
        error_msg = str(e)
        print(f"\n✗ Error setting up Firebase: {e}")
        
        # Check if database doesn't exist
        if "does not exist" in error_msg or "404" in error_msg:
            print("\n⚠ Firestore database does not exist for your project.")
            print("\nTo create the Firestore database:")
            print("1. Go to Firebase Console:")
            print("   https://console.firebase.google.com/project/" + project_id)
            print("2. Click 'Firestore Database' in the left sidebar")
            print("3. Click 'Create database'")
            print("4. Choose 'Start in test mode' (or production mode with your security rules)")
            print("5. Select a location (choose closest to you, e.g., us-central1)")
            print("6. Click 'Enable'")
            print("\n   OR create via Google Cloud Console:")
            print(f"   https://console.cloud.google.com/datastore/setup?project={project_id}")
            print("\n   Wait a few minutes for the database to be created, then run this script again.")
            return 1
        
        # Check if it's a Firestore API not enabled error
        if "SERVICE_DISABLED" in error_msg or "API has not been used" in error_msg or "it is disabled" in error_msg:
            print("\n⚠ Firestore API is not enabled for your project.")
            print("\nTo enable Firestore API:")
            print("1. Go to Firebase Console:")
            print("   https://console.firebase.google.com/project/" + project_id)
            print("2. Click 'Firestore Database' in the left sidebar")
            print("3. Click 'Create database'")
            print("4. Choose 'Start in test mode' (or production mode)")
            print("5. Select a location and click 'Enable'")
            print("\n   OR enable via Google Cloud Console:")
            print(f"   https://console.cloud.google.com/apis/library/firestore.googleapis.com?project={project_id}")
            print("\n   Click 'Enable' and wait a few minutes for changes to propagate.")
            print("\n   Then run this script again.")
        else:
            print("\nTroubleshooting:")
            print("1. Verify your service account JSON file is valid")
            print("2. Check that Firestore database exists:")
            print(f"   https://console.firebase.google.com/project/{project_id}/firestore")
            print("3. If database doesn't exist, create it:")
            print(f"   https://console.cloud.google.com/datastore/setup?project={project_id}")
            print("4. Ensure your project ID matches the JSON file")
            print("5. Get your Project ID from Firebase Console > Project Settings")
        
        return 1


if __name__ == "__main__":
    sys.exit(verify_firebase())
