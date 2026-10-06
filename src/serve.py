"""Production entry point: python -m src.serve (one process only)."""
import os
from dotenv import load_dotenv


def validate_environment(environ):
    secrets = [environ.get(name, "") for name in ("MANAGEMENT_PIN", "ENGINEERING_PIN", "HMI_DEVICE_PIN")]
    if any(len(value) < 12 or "replace" in value.lower() for value in secrets):
        raise ValueError("Configure three distinct access secrets of at least 12 characters.")
    if len(set(secrets)) != 3:
        raise ValueError("Management, Engineering and tablet secrets must differ.")
    if not environ.get("DATABASE_URL") or "REPLACE_" in environ["DATABASE_URL"]:
        raise ValueError("Configure the server database connection.")
    if environ.get("WEB_CONCURRENCY", "1") != "1":
        raise ValueError("This release requires one API worker and one replica: sessions are process-local.")


def main():
    load_dotenv()
    validate_environment(os.environ)
    import uvicorn
    uvicorn.run("src.api:app", host="127.0.0.1", port=int(os.getenv("PORT", "8000")), workers=1)


if __name__ == "__main__":
    main()
