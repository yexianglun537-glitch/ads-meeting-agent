from app.diarization import SpeakerTurn, assign_speakers


def test_words_are_regrouped_when_speaker_changes() -> None:
    segments = [
        {
            "start": 0.0,
            "end": 2.0,
            "text": "你好收到",
            "words": [
                {"start": 0.0, "end": 0.8, "text": "你好"},
                {"start": 1.0, "end": 1.8, "text": "收到"},
            ],
        }
    ]
    turns = [SpeakerTurn(0.0, 0.9, 7), SpeakerTurn(0.9, 2.0, 3)]

    result = assign_speakers(segments, turns)

    assert [(item["speaker_label"], item["text"]) for item in result] == [
        ("发言人 1", "你好"),
        ("发言人 2", "收到"),
    ]
    assert [(item["start"], item["end"]) for item in result] == [(0.0, 0.8), (1.0, 1.8)]


def test_first_heard_speaker_gets_first_anonymous_label() -> None:
    segments = [
        {"start": 0.0, "end": 0.8, "text": "先说", "words": []},
        {"start": 1.0, "end": 1.8, "text": "后说", "words": []},
    ]
    turns = [SpeakerTurn(0.0, 0.8, 9), SpeakerTurn(1.0, 1.8, 2)]

    result = assign_speakers(segments, turns)

    assert [item["speaker_label"] for item in result] == ["发言人 1", "发言人 2"]


def test_overlapping_speakers_mark_segment_for_manual_review() -> None:
    segments = [
        {
            "start": 0.0,
            "end": 1.0,
            "text": "同时发言",
            "words": [{"start": 0.0, "end": 1.0, "text": "同时发言"}],
        }
    ]
    turns = [SpeakerTurn(0.0, 1.0, 0), SpeakerTurn(0.3, 0.9, 1)]

    result = assign_speakers(segments, turns)

    assert result[0]["speaker_label"] == "发言人 1"
    assert result[0]["speaker_ambiguous"] is True


def test_unmatched_segment_falls_back_to_first_speaker() -> None:
    segments = [{"start": 4.0, "end": 5.0, "text": "没有匹配区间", "words": []}]

    result = assign_speakers(segments, [])

    assert result == [
        {
            "start": 4.0,
            "end": 5.0,
            "text": "没有匹配区间",
            "speaker_label": "发言人 1",
            "speaker_ambiguous": False,
        }
    ]


def test_word_in_segmentation_gap_uses_nearest_speaker() -> None:
    segments = [
        {
            "start": 0.0,
            "end": 1.0,
            "text": "连续内容",
            "words": [
                {"start": 0.2, "end": 0.7, "text": "连续"},
                {"start": 0.82, "end": 0.92, "text": "内容"},
            ],
        }
    ]
    turns = [SpeakerTurn(0.0, 0.8, 3), SpeakerTurn(1.2, 2.0, 8)]

    result = assign_speakers(segments, turns)

    assert len(result) == 1
    assert result[0]["speaker_label"] == "发言人 1"
    assert result[0]["text"] == "连续内容"
