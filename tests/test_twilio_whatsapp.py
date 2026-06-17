from fanpulse_agent.tools import send_whatsapp_digest


def test_live_twilio_whatsapp_send_posts_message(monkeypatch):
    calls = []

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"sid": "SM123", "status": "queued"}

    def fake_post(url, data, auth, timeout):
        calls.append({"url": url, "data": data, "auth": auth, "timeout": timeout})
        return FakeResponse()

    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "AC123")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "secret")
    monkeypatch.setenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")
    monkeypatch.delenv("FANPULSE_DISABLE_LIVE_TWILIO", raising=False)
    monkeypatch.setattr("fanpulse_agent.twilio_whatsapp_client.requests.post", fake_post)

    result = send_whatsapp_digest("+14155550123", "FanPulse digest")

    assert result.success is True
    assert result.mock is False
    assert result.data["sent"] is True
    assert result.data["delivery_status"] == "queued"
    assert result.data["message_sid"] == "SM123"
    assert calls[0]["data"]["From"] == "whatsapp:+14155238886"
    assert calls[0]["data"]["To"] == "whatsapp:+14155550123"
    assert calls[0]["data"]["Body"] == "FanPulse digest"
    assert calls[0]["auth"] == ("AC123", "secret")


def test_live_twilio_whatsapp_send_formats_plain_from_number(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"sid": "SM456", "status": "sent"}

    captured = {}

    def fake_post(url, data, auth, timeout):
        captured.update(data)
        return FakeResponse()

    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "AC123")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "secret")
    monkeypatch.setenv("TWILIO_WHATSAPP_FROM", "+14155238886")
    monkeypatch.delenv("FANPULSE_DISABLE_LIVE_TWILIO", raising=False)
    monkeypatch.setattr("fanpulse_agent.twilio_whatsapp_client.requests.post", fake_post)

    result = send_whatsapp_digest("14155550123", "Digest")

    assert result.success is True
    assert captured["From"] == "whatsapp:+14155238886"
    assert captured["To"] == "whatsapp:+14155550123"


def test_live_twilio_whatsapp_send_surfaces_provider_error(monkeypatch):
    class FakeHTTPError(Exception):
        pass

    class FakeResponse:
        text = "sandbox recipient has not joined"

        def raise_for_status(self):
            raise FakeHTTPError("400 Client Error")

    def fake_post(url, data, auth, timeout):
        return FakeResponse()

    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "AC123")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "secret")
    monkeypatch.setenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")
    monkeypatch.delenv("FANPULSE_DISABLE_LIVE_TWILIO", raising=False)
    monkeypatch.setattr("fanpulse_agent.twilio_whatsapp_client.requests.post", fake_post)

    result = send_whatsapp_digest("+14155550123", "FanPulse digest")

    assert result.success is False
    assert result.mock is False
    assert result.data["sent"] is False
    assert "400 Client Error" in result.error
    assert "sandbox recipient" in result.error


def test_whatsapp_send_stays_mock_when_twilio_disabled(monkeypatch):
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "AC123")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "secret")
    monkeypatch.setenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")
    monkeypatch.setenv("FANPULSE_DISABLE_LIVE_TWILIO", "1")

    result = send_whatsapp_digest("+14155550123", "FanPulse digest")

    assert result.success is True
    assert result.mock is True
    assert result.data["sent"] is False
    assert result.data["delivery_status"] == "mocked_not_sent"
