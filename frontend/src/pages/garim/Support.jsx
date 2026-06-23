import { useState } from "react";
import { useDocumentTitle } from "../../hooks/useDocumentTitle";
import { submitAbuseReport } from "../../utils/api";
import "../../css/garim-pages/Support.css";

import GarimPage from "../../components/garim/GarimPage";

export default function Support() {
  useDocumentTitle("고객문의 및 신고 · Garim");

  const [formType, setFormType] = useState("general");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [jobId, setJobId] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!title.trim() || !description.trim()) {
      alert("제목과 상세 내용을 모두 입력해주세요.");
      return;
    }

    setLoading(true);
    try {
      await submitAbuseReport({
        report_type: formType,
        title,
        description,
        target_job_id: jobId.trim() || undefined,
      });
      alert("정상적으로 접수되었습니다. 감사합니다.");
      setTitle("");
      setDescription("");
      setJobId("");
      setFormType("general");
    } catch (err) {
      alert(err.message || "접수 중 오류가 발생했습니다.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <GarimPage bodyClass="page-support" screenLabel="99 Support">
      <div className="support-page">
        <div className="support-header">
          <h1>고객센터 및 신고 접수</h1>
          <p>이용 중 불편하신 점이나 불법적인 콘텐츠 악용 사례 등을 신고해주세요.</p>
        </div>

        <div className="support-container">
          <form className="support-form" onSubmit={handleSubmit}>
            <div className="form-group">
              <label>문의 유형</label>
              <select value={formType} onChange={(e) => setFormType(e.target.value)} className="support-input">
                <option value="general">일반 문의</option>
                <option value="bug_report">버그 및 오탐지 신고</option>
                <option value="abuse_report">불법 콘텐츠 및 악용 신고</option>
                <option value="billing">결제 및 환불 문의</option>
                <option value="other">기타</option>
              </select>
            </div>

            <div className="form-group">
              <label>제목</label>
              <input
                type="text"
                placeholder="문의 제목을 입력하세요"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                className="support-input"
                maxLength={100}
              />
            </div>

            <div className="form-group">
              <label>관련 작업 ID (선택사항)</label>
              <input
                type="text"
                placeholder="관련된 파일의 Job ID가 있다면 입력해주세요"
                value={jobId}
                onChange={(e) => setJobId(e.target.value)}
                className="support-input"
              />
            </div>

            <div className="form-group">
              <label>상세 내용</label>
              <textarea
                placeholder="자세한 내용을 입력해주세요..."
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                className="support-textarea"
                rows={8}
              />
            </div>

            <button type="submit" className="mui-btn mui-btn--contained support-submit-btn" disabled={loading}>
              {loading ? "접수 중..." : "제출하기"}
            </button>
          </form>

          <aside className="support-sidebar">
            <div className="sidebar-card">
              <span className="material-icons card-icon">help_outline</span>
              <h3>자주 묻는 질문</h3>
              <p>문의하시기 전에 FAQ를 먼저 확인해 보시면 빠른 해결이 가능할 수 있습니다.</p>
              <a href="/faq" className="mui-btn mui-btn--outlined support-faq-btn">FAQ 보러가기</a>
            </div>
            
            <div className="sidebar-card">
              <span className="material-icons card-icon">security</span>
              <h3>안전한 서비스 환경</h3>
              <p>Garim은 이용자들의 안전한 서비스 이용을 위해 불법 콘텐츠 악용에 강력히 대응합니다.</p>
            </div>
          </aside>
        </div>
      </div>
    </GarimPage>
  );
}
