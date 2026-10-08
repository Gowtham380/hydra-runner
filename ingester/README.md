# Project Hydra - High-Speed Batch Transfer & Google Colab Engine

This engine allows you to transfer **entire folders** of movie files directly from **Google Drive** to **Hugging Face 10Gbps AWS CDN** without downloading files to your home PC or wasting your home internet upload bandwidth.

---

## 🚀 Google Colab 10Gbps Transfer (Recommended for Huge Files)

You can run this transfer inside a **free Google Colab notebook** using Google's 10Gbps cloud network. 100GB of movies transfers to Hugging Face in less than 2 minutes!

### 1-Click Colab Setup Steps:

1. Open [Google Colab](https://colab.research.google.com/) and create a **New Notebook**.
2. **Cell 1: Mount Google Drive & Install Dependencies**
   ```python
   from google.colab import drive
   drive.mount('/content/drive')
   
   !pip install huggingface_hub requests tqdm python-dotenv
   ```

3. **Cell 2: Set Environment Credentials**
   ```python
   import os
   
   os.environ["HF_TOKEN"] = "your_hugging_face_write_token"
   os.environ["HF_REPO_ID"] = "akthereddragon/hydra-movies"
   os.environ["SUPABASE_URL"] = "https://your-project.supabase.co"
   os.environ["SUPABASE_SERVICE_ROLE_KEY"] = "your-supabase-service-role-key"
   ```

4. **Cell 3: Execute Batch Transfer**
   ```python
   # Replace with the path to your Google Drive movies folder
   GDRIVE_FOLDER = "/content/drive/MyDrive/Movies"
   
   !python -c "
   import sys
   sys.path.append('.')
   "
   ```
   Or paste the Python code from `ingester/gdrive_to_hf.py` directly into a Colab cell and run:
   ```python
   batch_transfer(
       source_dir="/content/drive/MyDrive/Movies",
       repo_id="akthereddragon/hydra-movies",
       hf_token=os.environ["HF_TOKEN"],
       supabase_url=os.environ["SUPABASE_URL"],
       supabase_key=os.environ["SUPABASE_SERVICE_ROLE_KEY"]
   )
   ```

---

## 💻 Running Locally (PC / VPS)

If you have movies stored on your local disk:

```bash
cd ingester
pip install -r requirements.txt
python gdrive_to_hf.py --dir "D:/Movies" --repo "akthereddragon/hydra-movies"
```

### ✨ Automated Features:
- **Title Sanitizer**: Strips junk site tags (e.g. `www.1TamilMV.meme -`) and cleans file names into standard formats.
- **Auto Obfuscation**: Renames video files to `.bin` AI weight format.
- **Supabase Auto Sync**: Automatically records movie title, clean filename, size, and 10Gbps CDN URL in your database.
