(function () {
    "use strict";

    var tabs = document.querySelectorAll(".tab");
    var panels = document.querySelectorAll(".tab-panel");
    var submitBtn = document.getElementById("submit-btn");
    var loadingEl = document.getElementById("loading");
    var errorEl = document.getElementById("error");
    var resultsEl = document.getElementById("results");

    var textInput = document.getElementById("text-input");
    var charCount = document.getElementById("char-count");

    var dropZone = document.getElementById("drop-zone");
    var videoInput = document.getElementById("video-input");
    var fileSelected = document.getElementById("file-selected");
    var fileNameSpan = document.getElementById("file-name");
    var clearFileBtn = document.getElementById("clear-file");

    var activeTab = "text";
    var selectedFile = null;

    /* ---- Tab switching ---- */

    tabs.forEach(function (tab) {
        tab.addEventListener("click", function () {
            activeTab = tab.dataset.tab;
            tabs.forEach(function (t) {
                t.classList.toggle("active", t === tab);
                t.setAttribute("aria-selected", t === tab ? "true" : "false");
            });
            panels.forEach(function (p) {
                p.classList.toggle("active", p.id === "panel-" + activeTab);
            });
            hideError();
            hideResults();
        });
    });

    /* ---- Character count ---- */

    textInput.addEventListener("input", function () {
        charCount.textContent = textInput.value.length;
    });

    /* ---- Drag & drop ---- */

    dropZone.addEventListener("click", function () { videoInput.click(); });

    dropZone.addEventListener("dragover", function (e) {
        e.preventDefault();
        dropZone.classList.add("dragover");
    });
    dropZone.addEventListener("dragleave", function () {
        dropZone.classList.remove("dragover");
    });
    dropZone.addEventListener("drop", function (e) {
        e.preventDefault();
        dropZone.classList.remove("dragover");
        if (e.dataTransfer.files.length > 0) {
            setFile(e.dataTransfer.files[0]);
        }
    });

    videoInput.addEventListener("change", function () {
        if (videoInput.files.length > 0) {
            setFile(videoInput.files[0]);
        }
    });

    clearFileBtn.addEventListener("click", function (e) {
        e.stopPropagation();
        clearFile();
    });

    function setFile(file) {
        selectedFile = file;
        fileNameSpan.textContent = file.name + " (" + formatBytes(file.size) + ")";
        dropZone.querySelector(".drop-zone-text").hidden = true;
        fileSelected.hidden = false;
    }

    function clearFile() {
        selectedFile = null;
        videoInput.value = "";
        dropZone.querySelector(".drop-zone-text").hidden = false;
        fileSelected.hidden = true;
    }

    function formatBytes(bytes) {
        if (bytes < 1024) return bytes + " B";
        if (bytes < 1048576) return (bytes / 1024).toFixed(1) + " KB";
        return (bytes / 1048576).toFixed(1) + " MB";
    }

    /* ---- Submit ---- */

    submitBtn.addEventListener("click", function () {
        hideError();
        hideResults();

        if (activeTab === "text") {
            var text = textInput.value.trim();
            if (!text) { showError("Please enter some text to analyze."); return; }
            submitJSON("/api/analyze/text", { text: text });
        } else if (activeTab === "video") {
            if (!selectedFile) { showError("Please select a video file."); return; }
            submitVideo("/api/analyze/video", selectedFile);
        }
    });

    function submitJSON(endpoint, body) {
        showLoading();
        fetch(endpoint, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body)
        })
        .then(handleResponse)
        .catch(handleNetworkError);
    }

    function submitVideo(endpoint, file) {
        showLoading();
        var formData = new FormData();
        formData.append("file", file);
        fetch(endpoint, { method: "POST", body: formData })
            .then(handleResponse)
            .catch(handleNetworkError);
    }

    function handleResponse(resp) {
        hideLoading();
        if (!resp.ok) {
            return resp.json().then(function (data) {
                showError(data.detail || "Request failed with status " + resp.status);
            }).catch(function () {
                showError("Request failed with status " + resp.status);
            });
        }
        return resp.json().then(renderResults);
    }

    function handleNetworkError(err) {
        hideLoading();
        showError("Network error: " + err.message);
    }

    /* ---- UI helpers ---- */

    function showLoading() { loadingEl.hidden = false; submitBtn.disabled = true; }
    function hideLoading() { loadingEl.hidden = true; submitBtn.disabled = false; }
    function showError(msg) { errorEl.textContent = msg; errorEl.hidden = false; }
    function hideError() { errorEl.hidden = true; }
    function hideResults() { resultsEl.hidden = true; }

    /* ---- Render results ---- */

    function renderResults(data) {
        var r = data.result;

        // AI-Generated prediction
        var prob = r.ai_generated.probability;
        var label = r.ai_generated.label;
        var barEl = document.getElementById("ai-bar");
        var labelEl = document.getElementById("ai-label");
        var probEl = document.getElementById("ai-probability");
        var reasonEl = document.getElementById("ai-reasoning");

        barEl.style.width = (prob * 100).toFixed(0) + "%";
        if (label === "ai_generated") {
            barEl.style.background = "#ef4444";
            labelEl.style.background = "rgba(239, 68, 68, 0.15)";
            labelEl.style.color = "#ef4444";
            labelEl.textContent = "AI Generated";
        } else if (label === "human_generated") {
            barEl.style.background = "#22c55e";
            labelEl.style.background = "rgba(34, 197, 94, 0.15)";
            labelEl.style.color = "#22c55e";
            labelEl.textContent = "Human Generated";
        } else {
            barEl.style.background = "#eab308";
            labelEl.style.background = "rgba(234, 179, 8, 0.15)";
            labelEl.style.color = "#eab308";
            labelEl.textContent = "Uncertain";
        }
        probEl.textContent = (prob * 100).toFixed(0) + "% probability";
        reasonEl.textContent = r.ai_generated.reasoning;

        // Virality score
        var score = r.virality.score;
        var viralBar = document.getElementById("virality-bar");
        var viralScore = document.getElementById("virality-score");
        var viralReason = document.getElementById("virality-reasoning");

        viralBar.style.width = score + "%";
        if (score < 30) {
            viralBar.style.background = "#6b7280";
        } else if (score < 60) {
            viralBar.style.background = "#eab308";
        } else {
            viralBar.style.background = "#22c55e";
        }
        viralScore.textContent = score;
        viralReason.textContent = r.virality.reasoning;

        // Distribution
        var grid = document.getElementById("audience-grid");
        grid.innerHTML = "";
        r.distribution.segments.forEach(function (seg) {
            var card = document.createElement("div");
            card.className = "audience-card";
            card.innerHTML = "<strong>" + escapeHtml(seg.audience) + "</strong>"
                           + "<p>" + escapeHtml(seg.resonance_reason) + "</p>";
            grid.appendChild(card);
        });

        // Summary
        document.getElementById("summary-text").textContent = r.summary;

        resultsEl.hidden = false;
        resultsEl.scrollIntoView({ behavior: "smooth", block: "start" });
    }

    function escapeHtml(str) {
        var div = document.createElement("div");
        div.appendChild(document.createTextNode(str));
        return div.innerHTML;
    }
})();
