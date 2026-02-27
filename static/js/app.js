document.addEventListener('DOMContentLoaded', () => {
    console.log("Nostradamus Pick-all Frontend Loaded");

    // 글로벌 상태
    const isLoggedIn = document.body.getAttribute('data-logged-in') === 'true';
    window.translationCache = {};

    async function translateIssueText(text, targetLang) {
        if (!text) return text;
        if (targetLang === 'en') return text;
        const cacheKey = `${text}_${targetLang}`;
        if (window.translationCache[cacheKey]) return window.translationCache[cacheKey];

        try {
            const url = `https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl=${targetLang}&dt=t&q=${encodeURIComponent(text)}`;
            const res = await fetch(url);
            const data = await res.json();
            const translated = data[0][0][0];
            window.translationCache[cacheKey] = translated;
            return translated;
        } catch (e) {
            console.error('Translation failed', e);
            return text;
        }
    }

    // --- 1. 다국어 (Internationalization) 로직 ---
    const translations = {
        'en': {
            'title': 'NostraDamu Pick',
            'header_open_issues': '── Open Predictions ────────────',
            'no_open_issues': 'No open predictions at the moment.',
            'loading_issues': 'Loading issues...',
            'header_recent_results': '── Recent Results ────────────',
            'no_resolved_issues': 'No resolved issues yet.',
            'header_leaderboard': 'Leaderboard',
            'header_my_stats': '── My Stats ──',
            'stat_rank': 'Rank',
            'stat_streak': 'Streak',
            'stat_wins': 'Wins',
            'msg_join_predict': 'Join a prediction to get on the leaderboard!',
            'btn_yes': '👍 YES',
            'btn_no': '👎 NO',
            'btn_voted_yes': '✅ Voted (YES)',
            'btn_voted_no': '✅ Voted (NO)',
            'total_pool': 'Total Pool',
            'pts': 'pts',
            'remaining': 'remaining',
            'closed': '⏰ Closed',
            'header_closed_issues': '── Closed Predictions ────────────',
            'no_closed_issues': 'No closed predictions yet.',
            'refresh_info': 'Answers are refreshed twice a day (UTC 00:00, 12:00).',
            'msg_voting_recorded': 'Your vote has been recorded!',
            'msg_login_required': 'Please login to vote.',
            'processing': '⏳ Processing...'
        },
        'ko': {
            'title': '노스트라다찍어.',
            'header_open_issues': '── 진행 중인 예측 ────────────',
            'no_open_issues': '현재 진행 중인 예측이 없습니다.',
            'loading_issues': '문제를 불러오는 중...',
            'header_recent_results': '── 최근 결과 ────────────',
            'no_resolved_issues': '아직 확정된 결과가 없습니다.',
            'header_leaderboard': '리더보드',
            'header_my_stats': '── 내 통계 ──',
            'stat_rank': '순위',
            'stat_streak': '연승',
            'stat_wins': '승리',
            'msg_join_predict': '예측에 참가하여 랭킹에 이름을 올리세요!',
            'btn_yes': '👍 예',
            'btn_no': '👎 아니오',
            'btn_voted_yes': '✅ 본 투표 (YES)',
            'btn_voted_no': '✅ 본 투표 (NO)',
            'total_pool': '총 상금',
            'pts': '포인트',
            'remaining': '남음',
            'closed': '⏰ 마감됨',
            'header_closed_issues': '── 마감된 예측 ────────────',
            'no_closed_issues': '마감된 예측이 없습니다.',
            'refresh_info': '정답은 하루 두 번(UTC 0시, 12시)에 갱신됩니다.',
            'msg_voting_recorded': '투표가 기록되었습니다!',
            'msg_login_required': '로그인이 필요한 서비스입니다.',
            'processing': '⏳ 처리 중...'
        },
        'ja': {
            'title': 'ノストラダ撮影',
            'header_open_issues': '── 進行中の予測 ────────────',
            'loading_issues': '読み込み中...',
            'header_recent_results': '── 最近の結果 ────────────',
            'no_resolved_issues': 'まだ確定した結果はありません。',
            'header_leaderboard': 'リーダーボード',
            'header_my_stats': '── マイ統計 ──',
            'stat_rank': '順位',
            'stat_streak': '連勝',
            'stat_wins': '勝利',
            'msg_join_predict': '予測に参加してランキングに名を連ねましょう！',
            'btn_yes': '👍 はい',
            'btn_no': '👎 いいえ',
            'btn_voted_yes': '✅ 投票済み (YES)',
            'btn_voted_no': '✅ 投票済み (NO)',
            'total_pool': '総プール',
            'pts': 'ポイント',
            'remaining': '残り',
            'closed': '⏰ 終了',
            'msg_voting_recorded': '投票が記録されました！',
            'msg_login_required': 'ログインが必要です。',
            'processing': '⏳ 処理中...'
        }
    };

    // 언어 감지 및 설정
    let currentLang = localStorage.getItem('userLang');
    if (!currentLang) {
        // 브라우저 언어 감지 (앞에 2자리만, 예: en-US -> en)
        const browserLang = (navigator.language || navigator.userLanguage).substring(0, 2).toLowerCase();
        currentLang = translations[browserLang] ? browserLang : 'en';
        localStorage.setItem('userLang', currentLang);
    }

    const langSelect = document.getElementById('langSelect');
    if (langSelect) {
        langSelect.value = currentLang;
        langSelect.addEventListener('change', (e) => {
            const newLang = e.target.value;
            localStorage.setItem('userLang', newLang);
            currentLang = newLang; // 전역상태 업데이트
            updateAppLanguage(newLang);
            loadIssues(); // 동적 요소 다시 랜더링
        });
    }

    // 번역 헬퍼 함수
    function t(key) {
        const langData = translations[currentLang] || translations['en'];
        return langData[key] || translations['en'][key] || key;
    }

    function updateAppLanguage(lang) {
        currentLang = lang;
        const titleText = t('title');
        const logoElements = document.querySelectorAll('.logo');
        logoElements.forEach(el => el.textContent = `🔮 ${titleText}`);
        document.title = titleText;

        // 정적 HTML 요소 번역 (data-i18n 속성 활용)
        document.querySelectorAll('[data-i18n]').forEach(el => {
            const key = el.getAttribute('data-i18n');
            el.textContent = t(key);
        });
    }

    // 초기 언어 적용
    updateAppLanguage(currentLang);

    // --- 2. 동적 데이터 로딩 (Issues & Leaderboard) ---
    async function loadIssues(retryCount = 0) {
        const issuesContainer = document.querySelector('.issues-list');
        const closedContainer = document.querySelector('.issues-list-closed');
        const resultsContainer = document.querySelector('.results-list');
        if (!issuesContainer) return;

        try {
            const resp = await fetchAPI('/api/issues/open');
            if (!resp.success) {
                if (retryCount < 2) {
                    console.log(`Retrying loadIssues... (${retryCount + 1})`);
                    setTimeout(() => loadIssues(retryCount + 1), 500);
                    return;
                }
                issuesContainer.innerHTML = `<p style="text-align:center; color:var(--text-muted); padding:20px;">Error: ${resp.error || 'Failed to load issues'}</p>`;
                return;
            }

            issuesContainer.innerHTML = '';
            if (closedContainer) closedContainer.innerHTML = '';
            if (resultsContainer) resultsContainer.innerHTML = '';

            if (!resp.data || resp.data.length === 0) {
                issuesContainer.innerHTML = `<p style="text-align:center; color:var(--text-muted); padding:20px;">${t('no_open_issues')}</p>`;
                if (closedContainer) closedContainer.innerHTML = `<p style="text-align:center; color:var(--text-muted); padding:20px;">${t('no_closed_issues')}</p>`;
                if (resultsContainer) resultsContainer.innerHTML = `<p style="text-align:center; color:var(--text-muted); padding:20px;">아직 확정된 결과가 없습니다.</p>`;
                return;
            }

            let openCount = 0;
            let closedCount = 0;
            let resolvedCount = 0;

            // 병렬 실행 제한 (Batching): 너무 많은 동시 번역 요청으로 인한 'Server disconnected' 방지
            const batchSize = 5;
            const results = [];
            for (let i = 0; i < resp.data.length; i += batchSize) {
                const batch = resp.data.slice(i, i + batchSize);
                const batchPromises = batch.map(async (issue) => {
                    const yesOpt = issue.options.find(o => o.title === 'Yes') || { pool_amount: 0, percent: 50 };
                    const noOpt = issue.options.find(o => o.title === 'No') || { pool_amount: 0, percent: 50 };

                    const [translatedTitle, translatedCategory] = await Promise.all([
                        translateIssueText(issue.title, currentLang),
                        translateIssueText(issue.category, currentLang)
                    ]);

                    const yesPercent = yesOpt.percent || 0;
                    const noPercent = noOpt.percent || 0;
                    const isResolved = issue.status === 'RESOLVED';
                    const isClosed = isResolved || new Date(issue.close_at).getTime() < new Date().getTime();

                    const card = document.createElement('div');
                    card.className = 'issue-card';
                    if (isClosed && !isResolved) card.classList.add('closed-card');
                    if (isResolved) card.classList.add('resolved-card');

                    card.innerHTML = `
                        <span class="category-tag" style="background:var(--bg-color); color:var(--text-main);">🏷️ ${translatedCategory.toUpperCase()}</span>
                        <h3 class="issue-question">${translatedTitle}</h3>
                        <div class="deadline-timer" data-deadline="${issue.close_at}">
                            ${isResolved ? '🏁 <strong>결과 발표 완료</strong>' : `⏰ ${t('loading_issues')}`}
                        </div>
                        <div class="bet-buttons" data-issue-id="${issue.id}">
                            <button class="bet-btn bet-btn-yes" data-issue-id="${issue.id}" data-option-id="${yesOpt.id}" ${isClosed ? 'disabled style="opacity:0.6; cursor:not-allowed;"' : ''}>${t('btn_yes')}</button>
                            <button class="bet-btn bet-btn-no" data-issue-id="${issue.id}" data-option-id="${noOpt.id}" ${isClosed ? 'disabled style="opacity:0.6; cursor:not-allowed;"' : ''}>${t('btn_no')}</button>
                        </div>
                        <div class="progress-bar" style="display: flex; background: var(--border-color); border-radius: 8px; overflow: hidden; margin-top: 12px; height: 30px;">
                            <div class="progress-yes" style="width: ${yesPercent > 0 ? yesPercent : 0}%; background: var(--yes-color); color: white; padding: 4px; text-align: left; font-size: 0.8rem; display: ${yesPercent > 0 ? 'block' : 'none'};">
                                Yes ${yesPercent}%
                            </div>
                            <div class="progress-no" style="width: ${noPercent > 0 ? noPercent : 0}%; background: var(--no-color); color: white; padding: 4px; text-align: right; font-size: 0.8rem; display: ${noPercent > 0 ? 'block' : 'none'};">
                                ${noPercent}% No
                            </div>
                            ${yesPercent === 0 && noPercent === 0 ? `<div style="width: 100%; text-align: center; color: var(--text-muted); font-size: 0.8rem; line-height:30px;">0 Votes</div>` : ''}
                        </div>
                    `;
                    return { card, isClosed, isResolved, status: issue.status };
                });
                results.push(...(await Promise.all(batchPromises)));
            }

            results.forEach(({ card, isClosed, isResolved }) => {
                if (isResolved) {
                    if (resultsContainer) {
                        resultsContainer.appendChild(card);
                        resolvedCount++;
                    }
                } else if (isClosed) {
                    if (closedContainer) {
                        closedContainer.appendChild(card);
                        closedCount++;
                    }
                } else {
                    issuesContainer.appendChild(card);
                    openCount++;
                }
            });

            if (openCount === 0) issuesContainer.innerHTML = `<p style="text-align:center; color:var(--text-muted); padding:20px;">${t('no_open_issues')}</p>`;
            if (closedCount === 0 && closedContainer) closedContainer.innerHTML = `<p style="text-align:center; color:var(--text-muted); padding:20px;">${t('no_closed_issues')}</p>`;
            if (resolvedCount === 0 && resultsContainer) resultsContainer.innerHTML = `<p style="text-align:center; color:var(--text-muted); padding:20px;">아직 확정된 결과가 없습니다.</p>`;

            checkVotedIssues();
        } catch (err) {
            console.error("Error in loadIssues:", err);
            issuesContainer.innerHTML = `<p style="text-align:center; color:var(--text-muted); padding:20px;">Network Error</p>`;
        }
    }

    async function loadLeaderboard() {
        const rankList = document.querySelector('.ranking-list');
        if (!rankList) return;

        try {
            const resp = await fetchAPI('/api/leaderboard');
            if (resp.success && resp.data) {
                rankList.innerHTML = '';
                const medals = ['🥇', '🥈', '🥉'];
                resp.data.forEach((user, index) => {
                    const li = document.createElement('li');
                    li.style = "display:flex; justify-content:space-between; margin-bottom: 8px;";
                    const rankIcon = medals[index] || `#${index + 1}`;
                    li.innerHTML = `<span>${rankIcon} ${user.email.split('@')[0]}</span> <strong>${user.points} ${t('pts')}</strong>`;
                    rankList.appendChild(li);
                });
            } else {
                rankList.innerHTML = '<li>Failed to load.</li>';
            }
        } catch (err) {
            console.error("Leaderboard load failed", err);
        }
    }

    // --- 3. 이미 투표한 이슈 로드 및 버튼 차단 (Pre-fetch 최적화) ---
    async function checkVotedIssues() {
        if (!isLoggedIn) return;
        const resp = await fetchAPI('/api/bets/me');
        if (resp.success && resp.data) {
            // resp.data는 { issue_id: option_id } 형태
            for (const [issueId, votedOptionId] of Object.entries(resp.data)) {
                // 해당 이슈의 모든 버튼 비활성화 (마감 전/후 상관없이)
                const btns = document.querySelectorAll(`.bet-btn[data-issue-id="${issueId}"]`);
                btns.forEach(b => {
                    b.disabled = true;
                    // 마감된 이슈(.closed-card 내의 버튼)인 경우 기존 투명도가 0.6일 수 있음.
                    b.style.opacity = '0.4';
                    b.style.cursor = 'not-allowed';

                    const optionId = b.getAttribute('data-option-id');
                    // 내가 투표한 옵션에만 체크 표시 및 강조
                    if (String(optionId) === String(votedOptionId)) {
                        const originalText = b.textContent;
                        if (!originalText.includes('✅')) {
                            const cleanText = originalText.replace('☑', '').trim(); // 혹시 남아있을 수 있는 다른 문자 제거
                            // 텍스트 강제 업데이트
                            b.innerHTML = `✅ ${cleanText}`;
                            // 선택된 버튼은 뚜렷하게 보이도록 불투명도 1로 설정, 두꺼운 초록 테두리
                            b.style.border = '4px solid #28a745';
                            b.style.opacity = '1';
                            // 마감 여부 상관없이 내가 투표한 항목은 밝게 유지
                            b.style.filter = 'brightness(1.1)';
                            b.style.boxShadow = 'none'; // 이전 글로우 효과 제거
                        }
                    }
                });
            }
        }
    }
    // --- 통계 요약 (Rank, Streak, Wins 및 5개 최근 맞춘 문제) ---
    async function loadMyStats() {
        if (!isLoggedIn) return;
        try {
            const resp = await fetchAPI('/api/users/me/stats');
            if (resp.success && resp.data) {
                const statsDiv = document.querySelector('.my-stats ul');
                if (statsDiv) {
                    statsDiv.innerHTML = `
                        <li>📍 <span data-i18n="stat_rank">Rank</span>: #${resp.data.rank}</li>
                        <li>🔥 <span data-i18n="stat_streak">Streak</span>: ${resp.data.streak}</li>
                        <li>✅ <span data-i18n="stat_wins">Wins</span>: ${resp.data.wins}</li>
                    `;
                    updateAppLanguage(currentLang);
                }

                const recentDiv = document.querySelector('.my-recent-correct');
                if (recentDiv && resp.data.recent_correct && resp.data.recent_correct.length > 0) {
                    let htmlStr = `<h4 style="font-size:0.9rem; margin-top:16px; margin-bottom:8px;">${currentLang === 'ko' ? '내가 최근 맞춘 문제' : 'Recent Correct Answers'}</h4><ul style="list-style:none; padding-left:0; font-size:0.85rem; color:var(--text-main);">`;

                    const translatedIssues = await Promise.all(resp.data.recent_correct.map(async (issue) => {
                        const title = await translateIssueText(issue.title, currentLang);
                        return `<li>✔️ ${title}</li>`;
                    }));

                    htmlStr += translatedIssues.join('') + '</ul>';
                    recentDiv.innerHTML = htmlStr;
                }
            }
        } catch (err) {
            console.error("Stats load failed", err);
        }
    }

    // 초기 로딩 실행 (순차적으로 실행하여 서버 부하 분산)
    async function initApp() {
        console.log("Initializing App data...");
        await loadIssues();
        await new Promise(r => setTimeout(r, 100));
        await loadLeaderboard();
        await new Promise(r => setTimeout(r, 100));
        await loadMyStats();
    }

    initApp();

    // --- 4. 이벤트 위임(Event Delegation)을 이용한 베팅 처리 ---
    document.addEventListener('click', async (e) => {
        const btn = e.target.closest('.bet-btn');
        if (!btn) return;

        if (!isLoggedIn) {
            e.preventDefault();
            alert(t('msg_login_required'));
            window.location.href = '/auth/login';
            return;
        }

        const issueId = btn.getAttribute('data-issue-id');
        const optionId = btn.getAttribute('data-option-id');

        if (btn.disabled) return;

        btn.disabled = true;
        const originalText = btn.innerHTML;
        btn.innerHTML = t('processing');

        const resp = await fetchAPI('/api/bet', {
            method: 'POST',
            body: JSON.stringify({
                issue_id: issueId,
                option_id: optionId,
                amount: 100
            })
        });

        if (resp.success) {
            alert(t('msg_voting_recorded'));
            const parent = btn.closest('.bet-buttons');
            if (parent) {
                parent.querySelectorAll('.bet-btn').forEach(b => {
                    b.disabled = true;
                    b.style.opacity = '0.6';
                    b.style.cursor = 'not-allowed';
                });
            }
            btn.innerHTML = `✅ ${originalText}`;
            // 투표 후 전체 리스트를 다시 불러와 게이지바 업데이트
            loadIssues();
            loadLeaderboard();
        } else {
            alert(resp.error || "처리 중 오류가 발생했습니다.");
            btn.disabled = false;
            btn.innerHTML = originalText;
        }
    });

    // --- 5. 타이머 로직 (동적으로 생성된 요소도 대응하기 위해 매 루프마다 셀렉터 실행) ---
    setInterval(() => {
        const now = new Date().getTime();
        const timers = document.querySelectorAll('.deadline-timer[data-deadline]');
        timers.forEach(timer => {
            const deadline = new Date(timer.getAttribute('data-deadline')).getTime();
            const distance = deadline - now;

            if (distance < 0) {
                timer.textContent = t('closed');
            } else {
                const days = Math.floor(distance / (1000 * 60 * 60 * 24));
                const hours = Math.floor((distance % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
                const minutes = Math.floor((distance % (1000 * 60 * 60)) / (1000 * 60));
                const seconds = Math.floor((distance % (1000 * 60)) / 1000);

                let timeString = "⏰ ";
                if (days > 0) timeString += `${days}d `;
                timeString += `${hours}h ${minutes}m ${seconds}s ${t('remaining')}`;
                timer.textContent = timeString;
            }
        });
    }, 1000);
});

// 공통 API 통신 헬퍼 함수
async function fetchAPI(url, options = {}) {
    try {
        const response = await fetch(url, {
            ...options,
            headers: {
                'Content-Type': 'application/json',
                ...options.headers
            }
        });
        return await response.json();
    } catch (error) {
        console.error("API Fetch Error:", error);
        return { success: false, error: error.message };
    }
}
