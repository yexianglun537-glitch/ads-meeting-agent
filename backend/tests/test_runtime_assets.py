from tools import download_runtime_assets


def test_whisper_download_manifest_contains_every_required_runtime_file():
    assert set(download_runtime_assets.WHISPER_FILES) == {
        "config.json",
        "model.bin",
        "tokenizer.json",
        "vocabulary.txt",
    }
    assert all(
        url.endswith(f"/resolve/main/{name}")
        for name, url in download_runtime_assets.WHISPER_FILES.items()
    )
