import io
from unittest.mock import patch

import pytest
from django.test import override_settings
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from rest_framework.exceptions import ValidationError

from apps.assistant.local_models import cosine, describe_image, embeddings, local_call
from apps.assistant.providers import ProviderProtocolError, ProviderUnavailable


def test_local_inference_rejects_remote_hosts():
    with pytest.raises(ProviderUnavailable):
        local_call("https://example.com/v1", "/embeddings", {})


@override_settings(AI_LOCAL_EMBEDDING_URL="http://127.0.0.1:8082/v1", AI_LOCAL_EMBEDDING_MODEL="test")
def test_embeddings_validate_order_and_reject_bad_vectors():
    with patch("apps.assistant.local_models.local_call", return_value={"data": [
        {"index": 1, "embedding": [0, 1]}, {"index": 0, "embedding": [1, 0]},
    ]}):
        assert embeddings(["耳机", "雨伞"]) == [[1, 0], [0, 1]]
    with patch("apps.assistant.local_models.local_call", return_value={"data": [
        {"index": 0, "embedding": [float("nan"), 0]},
    ]}):
        with pytest.raises(ProviderProtocolError):
            embeddings(["耳机"])
    assert cosine([1, 0], [1, 0]) == 1


@override_settings(AI_LOCAL_VISION_URL="http://127.0.0.1:8083/v1", AI_LOCAL_VISION_MODEL="test")
def test_vision_reencodes_valid_image_and_redacts_contact_details():
    buffer = io.BytesIO()
    Image.new("RGB", (16, 16), "black").save(buffer, "PNG")
    with patch("apps.assistant.local_models.local_call", return_value={"choices": [
        {"message": {"content": "黑色耳机，13800138000"}},
    ]}) as call:
        output = describe_image(SimpleUploadedFile("test.png", buffer.getvalue()))
        assert "13800138000" not in output
        content = call.call_args.args[2]["messages"][0]["content"]
        assert content[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    with pytest.raises(ValidationError):
        describe_image(SimpleUploadedFile("fake.png", b"not an image"))
