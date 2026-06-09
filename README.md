# Garmin FIT Backup

Automatic backup tool for downloading and archiving FIT activity files from Garmin Connect.

This script uses the unofficial `garminconnect` Python library to periodically sync your activities and store them locally in an organized folder structure.

---

## 🚀 Features

* 🔄 Automatic incremental sync (only new activities)
* 📦 Full bulk download on first run
* 🗂 Organized FIT storage by year/month
* 🧠 Resume-safe (uses `.garmin_last_sync`)
* ⚡ Pagination support for large activity histories
* 🛡 Rate-limit handling (Garmin 429 protection)
* 📊 Simple logging with rotation
* ⏱ Cron-friendly (runs unattended)

---

## 📁 Output structure

FIT files are stored like this:

```
garmin-fit/
 ├── 2024/
 │    ├── 01/
 │    │    ├── 2024-01-12_1234567890.fit
 │    │    └── ...
 │    └── 02/
 └── 2025/
```

---

## ⚙️ Requirements

* Python 3.9+
* `garminconnect` library

Install dependencies:

```bash
pip install garminconnect
```

---

## 🔐 Configuration

All configuration is handled via environment variables:

| Variable           | Description                                    |
| ------------------ | ---------------------------------------------- |
| `GARMIN_EMAIL`     | Garmin Connect login email                     |
| `GARMIN_PASSWORD`  | Garmin Connect password                        |
| `GARMIN_FIT_DIR`   | Output directory (default: `~/garmin-fit`)     |
| `GARMIN_LOOKBACK`  | Days to look back in bulk mode (default: 3650) |
| `GARMIN_PAGE_SIZE` | Activities per request (default: 100)          |

---

## ▶️ Usage

Run manually:

```bash
python3 garmin_backup.py
```

Or via wrapper script:

```bash
bash run_garmin_backup.sh
```

---

## ⏰ Automation (cron)

Example: run every 30 minutes

```bash
*/30 * * * * /path/to/run_garmin_backup.sh
```

---

## 🧠 How it works

1. Logs into Garmin Connect using stored credentials
2. Fetches activity list via paginated API calls
3. Compares activities with last sync timestamp
4. Downloads missing FIT files
5. Stores files locally in structured folders
6. Updates sync checkpoint

---

## 🔒 Security notes

* Credentials are stored in a local wrapper script
* Wrapper script is protected with `chmod 700`
* Garmin session tokens are cached locally to reduce login frequency

⚠️ This is an unofficial integration and may break if Garmin changes their API.

---

## ⚠️ Disclaimer

This project is not affiliated with Garmin. Use at your own risk.

---

## 📌 License

MIT License
