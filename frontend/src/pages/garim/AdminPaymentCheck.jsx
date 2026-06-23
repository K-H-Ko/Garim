import { useEffect, useState } from "react";
import { useDocumentTitle } from "../../hooks/useDocumentTitle";
import "../../css/garim-pages/AdminPaymentCheck.css";
import GarimPage from "../../components/garim/GarimPage";
import { getAdminPayments, getAdminPaymentDetail, refundAdminPayment } from "../../utils/api";

function formatDateParam(date) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function getRecent7DayRange() {
  const to = new Date();
  const from = new Date();
  from.setDate(to.getDate() - 7);
  return {
    from: formatDateParam(from),
    to: formatDateParam(to),
  };
}

export default function AdminPaymentCheck() {
  useDocumentTitle("사용자 결제 확인 · Garim Admin");

  const [activeTab, setActiveTab] = useState("all"); // "all" | "refund"
  const [productType, setProductType] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");
  const [searchKey, setSearchKey] = useState("email");
  const [searchValue, setSearchValue] = useState("");
  const [dateFrom, setDateFrom] = useState(() => getRecent7DayRange().from);
  const [dateTo, setDateTo] = useState(() => getRecent7DayRange().to);
  const [pageLimit, setPageLimit] = useState(10);
  const [currentPage, setCurrentPage] = useState(1);
  const [queryVersion, setQueryVersion] = useState(0);

  // 실데이터 상태
  const [payments, setPayments] = useState([]);
  const [summary, setSummary] = useState({
    today_amount: 0,
    success_count: 0,
    refund_count: 0,
    credit_count: 0,
  });
  const [total, setTotal] = useState(0);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);

  // 모달 상태
  const [detailModalOpen, setDetailModalOpen] = useState(false);
  const [selectedPaymentId, setSelectedPaymentId] = useState(null);
  const [detailData, setDetailData] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState(null);
  const [refundConfirmOpen, setRefundConfirmOpen] = useState(false);
  const [refundMessage, setRefundMessage] = useState("");

  // API 호출 핸들러
  const loadPayments = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const res = await getAdminPayments({
        page: currentPage,
        limit: pageLimit,
        product_type: productType,
        status: activeTab === "refund" ? "refunded" : statusFilter,
        q: searchValue,
        search_key: searchKey,
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
      });
      setPayments(res.data || []);
      setSummary(
        res.summary || {
          today_amount: 0,
          success_count: 0,
          refund_count: 0,
          credit_count: 0,
        }
      );
      setTotal(res.total || 0);
    } catch (err) {
      console.error("Failed to load payments", err);
      setError(err.message || "결제 내역을 불러오는데 실패했습니다.");
    } finally {
      setIsLoading(false);
    }
  };

  // 탭, 페이지, 개수, 명시적 검색/초기화 트리거 변경 시 자동 조회
  useEffect(() => {
    if (!dateFrom || !dateTo) return;
    loadPayments();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab, currentPage, pageLimit, queryVersion, dateFrom, dateTo]);

  // 탭 변경 시 상태 및 페이지 초기화
  const handleTabChange = (tab) => {
    setActiveTab(tab);
    setCurrentPage(1);
  };

  // 초기화 핸들러
  const handleReset = () => {
    const range = getRecent7DayRange();
    setProductType("all");
    setStatusFilter("all");
    setSearchKey("email");
    setSearchValue("");
    setDateFrom(range.from);
    setDateTo(range.to);
    setPageLimit(10);
    setCurrentPage(1);
    setActiveTab("all");
    setQueryVersion((v) => v + 1);
  };

  // 검색 실행 핸들러
  const handleSearch = (e) => {
    if (e) e.preventDefault();
    if (currentPage === 1) {
      setQueryVersion((v) => v + 1);
    } else {
      setCurrentPage(1);
    }
  };

  // 주문 식별자 마스킹 규칙 적용 함수
  const maskPaymentId = (uuid) => {
    if (!uuid) return "";
    return `${uuid.substring(0, 8)}...${uuid.substring(uuid.length - 5)}`;
  };

  const formatMoney = (val) => {
    return Number(val || 0).toLocaleString("ko-KR");
  };

  const getStatusLabel = (status) => {
    switch (status) {
      case "success": return "승인 완료";
      case "pending": return "대기";
      case "canceled": return "취소";
      case "refunded": return "환불";
      case "failed": return "실패";
      case "ready": return "결제 대기";
      default: return status;
    }
  };

  const getRefundAvailability = (detail) => {
    if (!detail) {
      return { canRefund: false, label: "환불 불가" };
    }
    if (detail.status === "refunded") {
      return { canRefund: false, label: "이미 환불됨" };
    }
    if (detail.status === "canceled") {
      return { canRefund: false, label: "취소 완료" };
    }
    if (detail.status === "success" && Number(detail.balance_amount || 0) > 0) {
      return { canRefund: true, label: "환불 가능" };
    }
    return { canRefund: false, label: "환불 불가" };
  };

  const handleOpenDetail = async (payment) => {
    setSelectedPaymentId(payment.payment_id);
    setDetailModalOpen(true);
    setDetailLoading(true);
    setDetailError(null);
    setRefundConfirmOpen(false);
    setRefundMessage("");
    setRefundReason("");
    setDetailData(null);
    try {
      const res = await getAdminPaymentDetail(payment.payment_id);
      setDetailData(res.data);
    } catch (err) {
      console.error("Failed to load payment detail", err);
      setDetailError("결제 상세 정보를 불러오는데 실패했습니다. 잠시 후 다시 시도해주세요.");
    } finally {
      setDetailLoading(false);
    }
  };

  const handleRequestRefund = () => {
    if (!detailData) return;
    setRefundMessage("");

    // ── 환불 경고 조건 체크 ──
    const warnings = [];
    const userEmail = detailData.user_email || "해당 사용자";

    // 조건 1: 결제일 기준 14일 경과
    if (detailData.days_since_payment >= 14) {
      warnings.push(`[${userEmail}] 사용자는 결제일 기준 14일이 지난 사용자입니다.`);
    }
    // 조건 2: 충전 크레딧의 15% 이상 사용
    if (detailData.credit_amount > 0 && detailData.credit_used_ratio >= 15) {
      warnings.push(`[${userEmail}] 사용자는 충전 크레딧의 15% 이상 사용한 사용자입니다.`);
    }
    if (warnings.length > 0) {
      alert(`⚠️ 환불 주의 사항\n\n${warnings.join("\n\n")}`);
    }

    setRefundConfirmOpen(true);
  };

  // 환불 사유를 상태로 관리
  const [refundReason, setRefundReason] = useState("");

  const handleConfirmRefund = async () => {
    if (!detailData) return;

    // 환불 사유 유효성 검사
    const trimmedReason = refundReason.trim();
    if (!trimmedReason) {
      alert("환불 사유를 입력해주세요.");
      return;
    }
    if (trimmedReason.length > 30) {
      alert("환불 사유는 30글자 이내로 입력해주세요.");
      return;
    }

    setDetailLoading(true);
    setDetailError(null);
    try {
      await refundAdminPayment(detailData.payment_id, trimmedReason);
      setRefundMessage("환불 처리가 완료되었습니다.");
      setRefundConfirmOpen(false);
      setRefundReason("");
      const res = await getAdminPaymentDetail(detailData.payment_id);
      setDetailData(res.data);
      loadPayments();
    } catch (err) {
      console.error("Refund failed", err);
      setDetailError(err.message || "환불 처리에 실패했습니다.");
      setRefundMessage(`환불 처리 실패: ${err.message || "알 수 없는 오류"}`);
    } finally {
      setDetailLoading(false);
    }
  };

  const totalPages = Math.ceil(total / pageLimit) || 1;
  const startIdx = total === 0 ? 0 : (currentPage - 1) * pageLimit + 1;
  const endIdx = Math.min(currentPage * pageLimit, total);
  const refundAvailability = getRefundAvailability(detailData);

  return (
    <GarimPage bodyClass="" screenLabel="31 Admin Payment Check">
      <div className="adm-shell">
        <aside className="adm-side">
          <div className="sec">운영</div>
          <a href="/admin/monitoring">
            <span className="material-icons">monitor_heart</span>
            사용자 모니터링
          </a>
          <a href="/admin/queue">
            <span className="material-icons">queue</span>
            처리 큐
          </a>
          <a href="/admin/compliance">
            <span className="material-icons">verified_user</span>
            컴플라이언스
          </a>
          <div className="sec">시스템</div>
          <a href="/admin/users">
            <span className="material-icons">people</span>
            사용자
          </a>
          <a href="/admin/analytics">
            <span className="material-icons">analytics</span>
            분석
          </a>
          <a href="/admin/policy">
            <span className="material-icons">tune</span>
            정책 및 상품 관리
          </a>
          <a href="/admin/subscriptions">
            <span className="material-icons">subscriptions</span>
            구독 관리
          </a>
          <a href="/admin/payments" className="active">
            <span className="material-icons">payments</span>
            사용자 결제 확인
          </a>
                  <a href="/admin/reports">
            <span className="material-icons">report_problem</span>
            문의 내역
          </a>
        </aside>

        <main className="adm-main pm-adm-main">
          <div className="pm-content pm-content--wide">
            
            {/* 상단 헤더 영역 */}
            <div className="pm-page-head">
              <div>
                <h1>사용자 결제 확인</h1>
                <p>
                  사용자 결제 내역, 구독 상태, 크레딧 충전 이력을 검색하고 확인합니다.
                </p>
              </div>
            </div>

            {/* 탭 버튼 영역 */}
            <div className="pm-tabs" role="tablist">
              <button
                type="button"
                className={`pm-tab ${activeTab === "all" ? "active" : ""}`}
                onClick={() => handleTabChange("all")}
              >
                <span className="material-icons">payments</span>
                결제 내역
              </button>
              <button
                type="button"
                className={`pm-tab ${activeTab === "refund" ? "active" : ""}`}
                onClick={() => handleTabChange("refund")}
              >
                <span className="material-icons">assignment_return</span>
                환불/취소
              </button>
            </div>

            {/* 요약 카드 영역 */}
            <div className="pm-metric-row">
              <div className="pm-metric">
                <div className="lbl">오늘 결제 금액</div>
                <div className="num">{formatMoney(summary.today_amount)}<small>원</small></div>
                <div className="delta">오늘 승인된 성공 합계</div>
              </div>
              <div className="pm-metric ok">
                <div className="lbl">승인 완료</div>
                <div className="num">{formatMoney(summary.success_count)}<small>건</small></div>
                <div className="delta">전체 누적 승인 건수</div>
              </div>
              <div className="pm-metric err">
                <div className="lbl">환불/취소</div>
                <div className="num">{formatMoney(summary.refund_count)}<small>건</small></div>
                <div className="delta">전체 누적 환불 건수</div>
              </div>
              <div className="pm-metric info">
                <div className="lbl">크레딧 충전</div>
                <div className="num">{formatMoney(summary.credit_count)}<small>건</small></div>
                <div className="delta">전체 크레딧 결제 건수</div>
              </div>
            </div>

            {/* 목록 테이블 카드 */}
            <div className="pm-card">
              <div className="pm-card-head">
                <div>
                  <h2>결제 내역</h2>
                  <p>이메일, 주문 식별자, 사용자 ID, 상품명 기준으로 조회합니다.</p>
                </div>

                <div className="pm-card-controls">
                  <div className="pm-card-title-tools">
                    <select
                      className="pm-limit-select"
                      value={pageLimit}
                      onChange={(e) => {
                        setPageLimit(Number(e.target.value));
                        setCurrentPage(1);
                      }}
                      aria-label="페이지당 결제 내역 개수"
                    >
                      <option value={10}>10</option>
                      <option value={20}>20</option>
                      <option value={50}>50</option>
                      <option value={100}>100</option>
                    </select>
                    <span className="pm-limit-label">개씩 보기</span>
                  </div>

                  {/* 검색 및 필터 툴바 */}
                  <form className="pm-toolbar" onSubmit={handleSearch}>
                    <div className="pm-toolbar-filters">
                      <div className="pm-filter-group">
                        <label>상품 유형</label>
                        <select value={productType} onChange={(e) => setProductType(e.target.value)} aria-label="상품 유형">
                          <option value="all">전체 상품</option>
                          <option value="subscription">구독</option>
                          <option value="credit">크레딧</option>
                        </select>
                      </div>
                      <div className="pm-filter-group">
                        <label>결제 상태</label>
                        <select 
                          value={statusFilter} 
                          onChange={(e) => setStatusFilter(e.target.value)}
                          disabled={activeTab === "refund"}
                          aria-label="결제 상태"
                        >
                          <option value="all">전체 상태</option>
                          <option value="success">승인 완료</option>
                          <option value="pending">대기</option>
                          <option value="canceled">취소</option>
                          <option value="refunded">환불</option>
                          <option value="failed">실패</option>
                          <option value="ready">결제 대기</option>
                        </select>
                      </div>
                      
                      {/* 검색어 유형 및 검색어 입력 */}
                      <div className="pm-filter-group pm-search-group">
                        <label>검색 조건</label>
                        <div className="pm-search-input-wrap">
                          <select value={searchKey} onChange={(e) => setSearchKey(e.target.value)} aria-label="검색 조건">
                            <option value="email">이메일</option>
                            <option value="payment_id">주문 식별자</option>
                            <option value="user_id">사용자 ID</option>
                            <option value="product_name">상품명</option>
                          </select>
                          <input 
                            type="text" 
                            placeholder="검색어 입력" 
                            value={searchValue} 
                            onChange={(e) => setSearchValue(e.target.value)}
                            aria-label="검색어"
                          />
                        </div>
                      </div>

                      {/* 기간 필터 */}
                      <div className="pm-filter-group pm-date-range">
                        <label>기간</label>
                        <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} aria-label="기간 시작일" />
                        <span>~</span>
                        <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} aria-label="기간 종료일" />
                      </div>
                    </div>

                    <div className="pm-toolbar-actions">
                      <button type="submit" className="mui-btn mui-btn--contained pm-btn-search">
                        <span className="material-icons">search</span>검색
                      </button>
                      <button type="button" className="mui-btn mui-btn--outlined pm-btn-reset" onClick={handleReset}>
                        초기화
                      </button>
                    </div>
                  </form>
                </div>
              </div>

              {/* 결제 목록 테이블 */}
              <div className="pm-data-table">
                <div className="pm-data-row pm-data-head">
                  <span>결제일</span>
                  <span>사용자</span>
                  <span>주문 식별자</span>
                  <span>상품</span>
                  <span>금액</span>
                  <span>상태</span>
                  <span>결제수단</span>
                  <span>관리</span>
                </div>

                {isLoading && (
                  <div className="pm-loading">
                    불러오는 중입니다...
                  </div>
                )}

                {!isLoading && error && (
                  <div className="pm-error">
                    {error}
                  </div>
                )}

                {!isLoading && !error && payments.map((payment) => (
                  <div className="pm-data-row" key={payment.payment_id}>
                    <span className="pm-date-cell">{payment.paid_at.replace("T", " ")}</span>
                    <span className="pm-user-cell">
                      <strong>{payment.user_email || "—"}</strong>
                      <small>{payment.user_id}</small>
                    </span>
                    <span className="pm-uuid-cell mono">{maskPaymentId(payment.payment_id)}</span>
                    <span className="pm-product-cell">
                      <span className={`pm-prod-badge ${payment.product_type}`}>
                        {payment.product_type === "subscription" ? "구독" : "크레딧"}
                      </span>
                      <strong>{payment.product_name}</strong>
                    </span>
                    <span className="pm-amount-cell">₩{formatMoney(payment.amount)}</span>
                    <span className="pm-status-cell">
                      <span className={`pm-status ${payment.status}`}>
                        {getStatusLabel(payment.status)}
                      </span>
                    </span>
                    <span className="pm-method-cell">{payment.payment_method || "—"}</span>
                    <span className="pm-action-cell">
                      <button 
                        type="button" 
                        className="pm-btn-detail" 
                        onClick={() => handleOpenDetail(payment)}
                      >
                        상세
                      </button>
                    </span>
                  </div>
                ))}

                {!isLoading && !error && payments.length === 0 && (
                  <div className="pm-empty">
                    검색 결과가 없습니다.
                  </div>
                )}
              </div>

              {/* 페이지네이션 및 페이지당 개수 */}
              <div className="pm-pagination">
                <span className="meta">
                  {total === 0 ? "0건" : `${startIdx}-${endIdx} / ${total.toLocaleString()}`}
                </span>
                <div className="pm-pagination-actions">
                  <button 
                    type="button" 
                    className="mui-btn mui-btn--outlined mui-btn--sm" 
                    disabled={currentPage <= 1 || isLoading}
                    onClick={() => setCurrentPage((p) => p - 1)}
                  >
                    이전
                  </button>
                  <button 
                    type="button" 
                    className="mui-btn mui-btn--outlined mui-btn--sm" 
                    disabled={currentPage >= totalPages || isLoading}
                    onClick={() => setCurrentPage((p) => p + 1)}
                  >
                    다음
                  </button>
                </div>
              </div>

            </div>

          </div>
        </main>
      </div>

      {/* 상세 조회 모달 팝업 */}
      {detailModalOpen && (
        <div className="pm-modal-backdrop" onClick={() => setDetailModalOpen(false)}>
          <div className="pm-modal" onClick={(e) => e.stopPropagation()}>
            <div className="pm-modal-header">
              <h2>결제 상세 정보</h2>
              <button 
                type="button" 
                className="pm-modal-close" 
                onClick={() => setDetailModalOpen(false)}
              >
                <span className="material-icons">close</span>
              </button>
            </div>
            
            <div className="pm-modal-body">
              {detailLoading && (
                <div className="pm-modal-loading">
                  불러오는 중...
                </div>
              )}
              
              {detailError && (
                <div className="pm-modal-error">
                  {detailError}
                </div>
              )}
              
              {!detailLoading && !detailError && detailData && (
                <div className="pm-detail-panel">
                  <div className="pm-detail-status-line">
                    <span className={`pm-status ${detailData.status}`}>
                      {getStatusLabel(detailData.status)}
                    </span>
                    <span>
                      {(detailData.approved_at || detailData.paid_at || detailData.created_at || "").replace("T", " ")}
                    </span>
                  </div>

                  <div className="pm-detail-kv-row">
                    <div className="pm-detail-kv">
                      <span className="pm-detail-lbl">주문 식별자</span>
                      <strong className="pm-detail-val mono">{maskPaymentId(detailData.payment_id)}</strong>
                    </div>
                  </div>

                  <div className="pm-detail-info-card">
                    <div>
                      <span className="pm-detail-lbl">사용자</span>
                      <strong className="pm-detail-val">{detailData.user_email || "—"}</strong>
                      <small className="pm-detail-sub mono">{detailData.user_id || "—"}</small>
                    </div>
                    <div>
                      <span className="pm-detail-lbl">상품</span>
                      <strong className="pm-detail-val">
                        <span className={`pm-prod-badge ${detailData.product_type}`}>
                          {detailData.product_type === "subscription" ? "구독" : "크레딧"}
                        </span>{" "}
                        {detailData.product_name || "—"}
                      </strong>
                      <small className="pm-detail-sub">
                        {detailData.product_type === "subscription"
                          ? "구독 상품"
                          : `${detailData.credit_amount || 0} 크레딧 반영`}
                      </small>
                    </div>
                  </div>

                  <div className="pm-detail-payment-row">
                    <div>
                      <span className="pm-detail-lbl">결제 금액</span>
                      <strong className="pm-detail-amount">₩{formatMoney(detailData.amount)}</strong>
                    </div>
                    <div>
                      <span className="pm-detail-lbl">결제 수단</span>
                      <strong className="pm-detail-val">{detailData.payment_method || "—"}</strong>
                      <small className="pm-detail-sub">{detailData.pg_provider || "PG 정보 없음"} · KRW</small>
                    </div>
                  </div>

                  <div className="pm-detail-result-block">
                    <span className="pm-detail-lbl">처리 결과</span>
                    {detailData.product_type === "subscription" ? (
                      <div className="pm-detail-result-grid">
                        <div>
                          <strong>구독 처리 완료</strong>
                          <small className="mono">{detailData.subscription_id || "처리 완료"}</small>
                        </div>
                        <div>
                          <strong>크레딧 반영</strong>
                          <small>{detailData.credit_amount || 0} 크레딧</small>
                        </div>
                      </div>
                    ) : (
                      <div className="pm-detail-result-grid">
                        <div>
                          <strong>크레딧 충전 완료</strong>
                          <small>{detailData.credit_amount || 0} 크레딧</small>
                        </div>
                        <div>
                          <strong>원장 반영</strong>
                          <small className="mono">{detailData.credit_ledger_id || "처리 완료"}</small>
                        </div>
                      </div>
                    )}
                  </div>

                  <div className="pm-detail-refund-line">
                    <span className="pm-detail-lbl">환불 가능 여부</span>
                    <span className={`pm-refund-availability ${refundAvailability.canRefund ? "ok" : "disabled"}`}>
                      {refundAvailability.label}
                    </span>
                  </div>

                  {detailData.admin_note && (
                    <div className="pm-detail-note">{detailData.admin_note}</div>
                  )}
                </div>
              )}
            </div>

            <div className="pm-modal-footer">
              {refundMessage && (
                <div className="pm-refund-message" role="status">
                  {refundMessage}
                </div>
              )}
              {!detailLoading && !detailError && detailData && refundAvailability.canRefund && (
                <button 
                  type="button" 
                  className="mui-btn mui-btn--contained mui-btn--error pm-btn-refund"
                  onClick={handleRequestRefund}
                >
                  환불 처리
                </button>
              )}
              <button 
                type="button" 
                className="mui-btn mui-btn--outlined" 
                onClick={() => setDetailModalOpen(false)}
              >
                닫기
              </button>
            </div>
          </div>
        </div>
      )}

      {refundConfirmOpen && detailData && (
        <div className="pm-modal-backdrop pm-refund-confirm" onClick={() => setRefundConfirmOpen(false)}>
          <div className="pm-modal pm-refund-confirm-dialog" onClick={(e) => e.stopPropagation()}>
            <div className="pm-modal-header">
              <h2>환불 처리 확인</h2>
              <button
                type="button"
                className="pm-modal-close"
                onClick={() => setRefundConfirmOpen(false)}
              >
                <span className="material-icons">close</span>
              </button>
            </div>
            <div className="pm-modal-body">
              <p className="pm-refund-confirm-text">
                선택한 결제를 환불 처리할까요? 처리 후 결제 상태가 환불로 변경됩니다.
              </p>
              <div className="pm-detail-section pm-detail-section--full">
                <div className="pm-detail-row">
                  <span className="pm-detail-lbl">주문 식별자</span>
                  <span className="pm-detail-val mono">{maskPaymentId(detailData.payment_id)}</span>
                </div>
                <div className="pm-detail-row">
                  <span className="pm-detail-lbl">사용자 이메일</span>
                  <span className="pm-detail-val">{detailData.user_email || "—"}</span>
                </div>
                <div className="pm-detail-row">
                  <span className="pm-detail-lbl">상품명</span>
                  <span className="pm-detail-val">{detailData.product_name || "—"}</span>
                </div>
                <div className="pm-detail-row">
                  <span className="pm-detail-lbl">환불 대상 금액</span>
                  <span className="pm-detail-val price">₩{formatMoney(detailData.balance_amount || detailData.amount)}</span>
                </div>
              </div>

              {/* 환불 사유 입력 필드 */}
              <div className="pm-refund-reason-wrap">
                <label className="pm-detail-lbl" htmlFor="refund-reason-input">
                  환불 사유 <span className="pm-required-mark">*</span>
                </label>
                <input
                  id="refund-reason-input"
                  type="text"
                  className="pm-refund-reason-input"
                  placeholder="환불 사유를 30글자 이내로 요약해주세요"
                  maxLength={30}
                  value={refundReason}
                  onChange={(e) => setRefundReason(e.target.value)}
                  autoFocus
                />
                <span className="pm-char-counter">{refundReason.length}/30</span>
              </div>
            </div>
            <div className="pm-modal-footer">
              <button
                type="button"
                className="mui-btn mui-btn--outlined"
                onClick={() => setRefundConfirmOpen(false)}
                disabled={detailLoading}
              >
                취소
              </button>
              <button
                type="button"
                className="mui-btn mui-btn--contained mui-btn--error pm-btn-refund"
                onClick={handleConfirmRefund}
                disabled={detailLoading || !refundReason.trim()}
              >
                환불 처리
              </button>
            </div>
          </div>
        </div>
      )}
    </GarimPage>
  );
}
