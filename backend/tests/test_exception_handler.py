"""统一 API 错误封装的纯单元测试，不需要连接数据库。"""
from types import SimpleNamespace

from rest_framework.exceptions import ValidationError

from config.exceptions import api_exception_handler


def test_validation_error_uses_first_field_message():
    response = api_exception_handler(
        ValidationError({"non_field_errors": ["地点不属于当前校区"]}),
        {"request": SimpleNamespace(request_id="req-location")},
    )

    assert response.status_code == 400
    assert response.data["error"]["message"] == "地点不属于当前校区"
    assert response.data["error"]["fields"] == {
        "non_field_errors": ["地点不属于当前校区"]
    }
    assert response.data["error"]["request_id"] == "req-location"


def test_plain_validation_error_keeps_the_reason_instead_of_empty_braces():
    response = api_exception_handler(
        ValidationError('该信息已关联认领申请，不能删除。'),
        {'request': SimpleNamespace(request_id='req-delete')},
    )
    assert response.status_code == 400
    assert response.data['error']['message'] == '该信息已关联认领申请，不能删除。'
    assert response.data['error']['fields']['non_field_errors'] == ['该信息已关联认领申请，不能删除。']


def test_empty_validation_details_use_a_readable_fallback():
    response = api_exception_handler(ValidationError({}), {'request': SimpleNamespace(request_id='req-empty')})
    assert response.data['error']['message'] == '请求未能完成'
