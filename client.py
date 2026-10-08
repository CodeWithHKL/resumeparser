import requests
import os
import time
import json

# --- 1. Configuration & User Input ---
url = "http://127.0.0.1:8000/rank-resumes"
resume_folders = [
    "./INFORMATION-TECHNOLOGY",
    "./Resume",
    "./ENGINEERING"
]

print("="*60)
print("🚀 RESUME RANKING TERMINAL")
print("="*60)

# Take user input for keywords at runtime
target_keywords = input("👉 Enter keywords to search : ").strip()

if not target_keywords:
    print("❌ Error: You must enter at least one keyword to rank resumes.")
    exit()

# --- 2. Gather all files ---
files_to_send = []
for folder in resume_folders:
    if not os.path.exists(folder):
        print(f"⚠️  Warning: Folder '{folder}' not found. Skipping...")
        continue
    for filename in os.listdir(folder):
        if filename.lower().endswith(('.pdf', '.docx', '.jpg', '.jpeg', '.png')):
            file_path = os.path.join(folder, filename)
            # Open file in binary mode
            files_to_send.append(
                ('files', (filename, open(file_path, 'rb')))
            )

if not files_to_send:
    print(f"❌ No valid resumes found in folders: {resume_folders}")
else:
    print(f"\n📦 Found {len(files_to_send)} resumes. Starting stream...")
    print("="*95)
    print(f"{'FILENAME':<35} | {'SCORE':<5} | {'TIME (s)':<12} | {'MATCHED SKILLS'}")
    print("-" * 95)
    
    start_time = time.time()
    all_results = []

    try:
        # --- 3. Stream Request ---
        # We pass target_keywords directly into the data payload
        with requests.post(url, data={'skills': target_keywords}, files=files_to_send, stream=True) as response:
            if response.status_code == 200:
                for line in response.iter_lines():
                    if line:
                        # Decode the JSON chunk from the server
                        result = json.loads(line.decode('utf-8'))
                        all_results.append(result)

                        # Print the result immediately as it arrives
                        if result.get('status') != 'success':
                            print(f"{result['filename'][:35]:<35} | {'ERR':<5} | {'-':<12} | {result.get('error', '')}")
                            continue
                        skills_str = ", ".join(result.get('matched_skills', []))
                        print(f"{result['filename'][:35]:<35} | {result['score']:<5} | {result['time_taken_sec']:<12} | {skills_str}")
            else:
                print(f"❌ Server Error: {response.status_code} - {response.text}")

        # --- 4. Final Summary and Ranking ---
        end_time = time.time()
        total_roundtrip = round(end_time - start_time, 2)
        
        print("-" * 95)
        print(f"✅ Processing Complete! {len(all_results)} resumes analyzed in {total_roundtrip}s")
        print("-" * 95)

        if all_results:
            # Show the Top 10 Ranking
            print("\n🏆 TOP 10 RANKING:")
            print(f"{'RANK':<5} | {'SCORE':<5} | {'FILENAME'}")
            print("-" * 45)
            
            # Sort list by score descending
            all_results = [r for r in all_results if r.get('status') == 'success']
            all_results.sort(key=lambda x: x['score'], reverse=True)
            for i, rank in enumerate(all_results[:10], 1):
                print(f"{i:<5} | {rank['score']:<5} | {rank['filename']}")
            print("="*95)

    except Exception as e:
        print(f"❗ An error occurred during processing: {e}")
    
    finally:
        # --- 5. Clean up ---
        # Always close files to prevent memory leaks/file locking
        for _, file_tuple in files_to_send:
            file_tuple[1].close()

# Keep terminal open
input("\nDone! Press Enter to exit...")