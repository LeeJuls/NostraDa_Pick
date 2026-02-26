document.addEventListener('DOMContentLoaded', () => {
    console.log("Nostradamus Pick-all Frontend Loaded");
    
    // 언어 변경 이벤트 예시
    const langSelect = document.getElementById('langSelect');
    if(langSelect) {
        langSelect.addEventListener('change', (e) => {
            const lang = e.target.value;
            // TODO: API 서버에 유저 선호 언어 업데이트 요청
            console.log("Language changed to:", lang);
        });
    }
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
