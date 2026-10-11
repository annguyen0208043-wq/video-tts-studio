from app.services.storage_service import safe_filename


def test_safe_filename_handles_vietnamese_and_symbols():
    assert safe_filename("Giọng đọc: mở đầu?.wav") == "Giong-doc-mo-dau.wav"


def test_safe_filename_has_fallback():
    assert safe_filename("???", "asset") == "asset"

