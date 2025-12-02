from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

@app.route("/", methods=["POST"])
def send_email():
    data = request.get_json()
    email = data.get("email")
    code = data.get("code")

    resend_api_key = "re_NFFdfHV8_8ZxQ5WUayJe6VnL2RGX6BK73"
    sender = "noreply@umaklebs.com"

    payload = {
        "from": sender,
        "to": [email],
        "subject": "UMak-LEBS Verification Code",
        "text": f"Your verification code is: {code}"
    }

    res = requests.post(
        "https://api.resend.com/emails",
        headers={
            "Authorization": f"Bearer {resend_api_key}",
            "Content-Type": "application/json"
        },
        json=payload
    )

    return jsonify({"status": res.status_code, "response": res.text})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
