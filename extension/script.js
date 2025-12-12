document.addEventListener("DOMContentLoaded", async () => {
    const askBtn = document.getElementById("askBtn");
    const questionInput = document.getElementById("question");
    const chatContainer = document.getElementById("chatContainer");
    const statusText = document.getElementById("statusText");
    const popOutBtn = document.getElementById("popOutBtn");
  
    let currentVideoId = null;
  
    // --- 1. DETECT VIDEO ID ---
    const urlParams = new URLSearchParams(window.location.search);
    const poppedId = urlParams.get('v');
  
    if (poppedId) {
        currentVideoId = poppedId;
        statusText.textContent = "• Active";
        statusText.style.color = "#90ee90";
        popOutBtn.style.display = "none";
    } else {
        try {
            let [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
            if (tab && tab.url && tab.url.includes("youtube.com/watch")) {
                const urlParams = new URLSearchParams(new URL(tab.url).search);
                currentVideoId = urlParams.get("v");
                statusText.textContent = "• Connected";
                statusText.style.color = "#90ee90";
            } else {
                statusText.textContent = "• No Video";
                statusText.style.color = "#ffaaaa";
            }
        } catch (e) {
            console.error(e);
        }
    }
  
    // --- 2. POP OUT LOGIC ---
    popOutBtn.addEventListener("click", () => {
        if (!currentVideoId) {
            alert("Please open a YouTube video first!");
            return;
        }
        chrome.windows.create({
            url: `popup.html?v=${currentVideoId}`,
            type: "popup",
            width: 460,
            height: 600
        });
    });
  
    // --- 3. SEND MESSAGE ---
    questionInput.addEventListener("keypress", (e) => {
        if (e.key === "Enter") handleSend();
    });
  
    askBtn.addEventListener("click", handleSend);
  
    async function handleSend() {
        const question = questionInput.value.trim();
        if (!question || !currentVideoId) return;
  
        // 1. Add User Message
        addBubble(question, "user-message");
        questionInput.value = "";
        askBtn.disabled = true;
  
        // 2. Add Temporary "Thinking..." Bubble
        const loadingId = addBubble("Thinking...", "bot-message");
  
        try {
            const response = await fetch("http://127.0.0.1:8000/ask", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ video_id: currentVideoId, question: question })
            });
  
            if (!response.ok) throw new Error("Server Error");
  
            const data = await response.json();
            
            // 3. Process Answer
            let formattedText = data.answer.replace(/\n/g, "<br>");
            formattedText = formattedText.replace(
                /\[Watch\]\s*\((.*?)\)/g, 
                '<a href="$1" target="_blank">Watch ↗</a>'
            );
  
            // 4. OVERWRITE "Thinking..." with the Real Answer
            const loadingBubble = document.getElementById(loadingId);
            loadingBubble.innerHTML = formattedText;
  
        } catch (error) {
            // Overwrite "Thinking..." with Error
            const loadingBubble = document.getElementById(loadingId);
            loadingBubble.innerHTML = "❌ Error: Could not reach the AI server.";
            loadingBubble.style.color = "red";
        } finally {
            askBtn.disabled = false;
        }
    }
  
    function addBubble(text, className) {
        const div = document.createElement("div");
        div.className = `message ${className}`;
        div.innerHTML = text;
        div.id = "msg-" + Date.now();
        chatContainer.appendChild(div);
        chatContainer.scrollTop = chatContainer.scrollHeight;
        return div.id;
    }
});