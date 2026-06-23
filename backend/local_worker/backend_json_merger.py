import json
import os
import re
from pathlib import Path


def merge_visual_and_audio_reports(visual_index_path: str, audio_pii_segments: list, output_path: str = None):
    """시각 PII JSON + STT PII 배열 → 최종 _result.json 생성."""
    visual_index_path = Path(visual_index_path)
    output_path = Path(output_path) if output_path else visual_index_path

    with open(visual_index_path, 'r', encoding='utf-8') as f:
        merged_data = json.load(f)

    # STT 세그먼트 → audio_pii_groups 스키마 변환
    audio_pii_groups = []
    for idx, seg in enumerate(audio_pii_segments, 1):
        pii_type = seg.get("label", "unknown")
        audio_pii_groups.append({
            "pii_id":         f"음성_{pii_type}_{idx}",
            "pii_type":       pii_type,
            "detected_text":  seg.get("detected_text", ""),
            "is_selected":    False,
            "start_time_sec": seg.get("start_time_sec", 0.0),
            "end_time_sec":   seg.get("end_time_sec", 0.0),
            "confidence":     seg.get("confidence", 0.0)
        })

    audio_pii_count  = len(audio_pii_groups)
    visual_pii_count = merged_data.get("total_pii_count", len(merged_data.get("pii_groups", [])))
    total_count      = visual_pii_count + audio_pii_count

    # visual/audio/total 카운트를 기존 total_pii_count 위치에 묶어 삽입
    final_ordered_data = {}
    inserted = False
    for k, v in merged_data.items():
        if k == "total_pii_count":
            final_ordered_data["visual_pii_count"] = visual_pii_count
            final_ordered_data["audio_pii_count"]  = audio_pii_count
            final_ordered_data["total_pii_count"]  = total_count
            inserted = True
        elif k not in ["visual_pii_count", "audio_pii_count"]:
            final_ordered_data[k] = v

    if not inserted:
        final_ordered_data["visual_pii_count"] = visual_pii_count
        final_ordered_data["audio_pii_count"]  = audio_pii_count
        final_ordered_data["total_pii_count"]  = total_count

    final_ordered_data["audio_pii_groups"] = audio_pii_groups

    # 타임라인 마커 데이터 생성 후 result.json에 포함 (별도 JSON 불필요)
    try:
        from pipeline_detail_view import _build_timeline_markers
        total_duration = float(final_ordered_data.get('total_duration') or 0.0)
        if not total_duration:
            fps = float(final_ordered_data.get('fps') or 0)
            frames = int(final_ordered_data.get('total_frames') or 0)
            if fps > 0 and frames > 0:
                total_duration = frames / fps
        final_ordered_data["timeline_markers"] = _build_timeline_markers(final_ordered_data, total_duration)
    except Exception:
        final_ordered_data["timeline_markers"] = []

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(final_ordered_data, f, ensure_ascii=False, indent=2)

    return final_ordered_data


if __name__ == "__main__":

    OUTPUT_FILE_DIR = r"G:\내 드라이브\PJ(Human)\Final_PJ(Human_team)\Human_Final_PJ-main\output_file"
    STT_OUTPUT_DIR  = OUTPUT_FILE_DIR  # stt.json이 index.json과 동일 폴더에 생성됨

    # OCR_pipeline_report.py의 TEST_TARGET에서 타겟 파일명 자동 추출
    TARGET_NAME = "음성_영상1"
    try:
        report_py_path = os.path.join(os.path.dirname(__file__), "OCR_pipeline_report.py")
        with open(report_py_path, "r", encoding="utf-8") as f:
            match = re.search(r'TEST_TARGET\s*=\s*[rR]?["\'](.*?)["\']', f.read())
            if match:
                TARGET_NAME = os.path.splitext(os.path.basename(match.group(1)))[0]
                print(f"💡 타겟 파일명 자동 로드: '{TARGET_NAME}'")
    except Exception as e:
        print(f"⚠️ Report 설정 자동 불러오기 실패 (기본값 사용): {e}")

    visual_json_path  = os.path.join(OUTPUT_FILE_DIR, f"{TARGET_NAME}_index.json")
    stt_json_path     = os.path.join(STT_OUTPUT_DIR,  f"{TARGET_NAME}_stt.json")
    merged_output_path = os.path.join(OUTPUT_FILE_DIR, f"{TARGET_NAME}_result.json")

    print("🔄 JSON 병합 시작...")

    if not os.path.exists(visual_json_path):
        print(f"❌ 시각 분석 JSON 없음: {visual_json_path}")
    elif not os.path.exists(stt_json_path):
        print(f"❌ STT JSON 없음: {stt_json_path}")
    else:
        with open(stt_json_path, "r", encoding="utf-8") as f:
            stt_data = json.load(f)
        pii_segments = stt_data.get("results", {}).get("pii_detect", {}).get("pii_segments", [])

        try:
            final_data = merge_visual_and_audio_reports(
                visual_index_path=visual_json_path,
                audio_pii_segments=pii_segments,
                output_path=merged_output_path
            )
            print(f"✅ 병합 완료: {merged_output_path}")
            print(f"📊 시각({final_data.get('visual_pii_count', 0)}건) + 음성({final_data.get('audio_pii_count', 0)}건) = 전체({final_data.get('total_pii_count', 0)}건)")

            # 병합 완료 후 stt.json 삭제 (result.json만 남김)
            if os.path.exists(stt_json_path):
                os.remove(stt_json_path)
                print(f"🗑️  STT JSON 삭제 완료: {stt_json_path}")

            # merge 완료 직후 상세보기 데이터 미리 생성 (상세보기 클릭 시 즉시 표시용)
            print("\n🖼️  상세보기 데이터 생성 중 (로컬 CPU)...")
            try:
                from pipeline_detail_view import run_detail_view
                run_detail_view(merged_output_path)
                print("✅ 상세보기 파일 생성 완료 (output_file 폴더 확인)")
            except Exception as dv_err:
                print(f"⚠️  상세보기 생성 오류 (병합 결과는 정상): {dv_err}")

        except Exception as e:
            print(f"❌ 병합 오류: {e}")
