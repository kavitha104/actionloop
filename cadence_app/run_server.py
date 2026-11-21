import uvicorn
import sys
import os

if __name__ == "__main__":
    # Ensure current working directory is on python path
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    port = int(os.environ.get("PORT", os.environ.get("CADENCE_PORT", 8080)))
    print("==================================================================")
    print("🚀 Starting Cadence Meeting-to-Execution Agent Production Server")
    print(f"   Listening on: http://127.0.0.1:{port}")
    print(f"   API Documentation: http://127.0.0.1:{port}/docs")
    print("==================================================================")
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=False)
