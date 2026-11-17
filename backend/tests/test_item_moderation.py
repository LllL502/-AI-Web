from apps.items.moderation import moderate_public_text


def test_normal_lost_and_found_text_is_auto_approved():
    result = moderate_public_text("拾到黑色钥匙串", "在操场跑道旁拾到，已送到服务站")
    assert result.approved
    assert result.reasons == ()


def test_contact_or_external_link_is_kept_for_manual_review():
    result = moderate_public_text("拾到钥匙", "加我微信或打 13812345678，详见 https://example.test")
    assert not result.approved
    assert set(result.reasons) == {"手机号码", "网页链接", "社交联系方式"}
