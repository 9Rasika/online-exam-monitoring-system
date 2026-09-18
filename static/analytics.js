/* Candidate analytics uses native canvas, so it has no network dependency. */
const analyticsData = JSON.parse(document.getElementById("analytics-data").textContent);
const palette = ["#65b5ff", "#9f8cff", "#f4b74c", "#ed758b"];

function prepareCanvas(canvas) {
    const ratio = window.devicePixelRatio || 1;
    const width = Math.max(canvas.clientWidth, 280);
    const height = Math.max(canvas.clientHeight, 260);
    canvas.width = width * ratio;
    canvas.height = height * ratio;
    const context = canvas.getContext("2d");
    context.scale(ratio, ratio);
    return { context, width, height };
}

function drawEmptyState(context, width, height, message) {
    context.fillStyle = "#9fb5d7";
    context.font = "14px Arial";
    context.textAlign = "center";
    context.fillText(message, width / 2, height / 2);
}

function drawScoreTrend() {
    const canvas = document.getElementById("scoreTrendChart");
    const { context, width, height } = prepareCanvas(canvas);
    const points = analyticsData.score_timeline;
    const padding = { top: 22, right: 24, bottom: 40, left: 48 };
    const plotWidth = width - padding.left - padding.right;
    const plotHeight = height - padding.top - padding.bottom;

    if (!points.length) {
        drawEmptyState(context, width, height, "No score data is available.");
        return;
    }

    context.strokeStyle = "rgba(147, 185, 255, 0.18)";
    context.fillStyle = "#9fb5d7";
    context.font = "12px Arial";
    context.textAlign = "right";
    [0, 25, 50, 75, 100].forEach((score) => {
        const y = padding.top + plotHeight * (1 - score / 100);
        context.beginPath();
        context.moveTo(padding.left, y);
        context.lineTo(width - padding.right, y);
        context.stroke();
        context.fillText(score, padding.left - 9, y + 4);
    });

    const coordinates = points.map((point, index) => ({
        x: padding.left + (points.length === 1 ? plotWidth / 2 : (index / (points.length - 1)) * plotWidth),
        y: padding.top + plotHeight * (1 - Math.max(0, Math.min(100, point.score)) / 100),
    }));

    context.beginPath();
    coordinates.forEach((point, index) => {
        index ? context.lineTo(point.x, point.y) : context.moveTo(point.x, point.y);
    });
    context.lineTo(coordinates[coordinates.length - 1].x, padding.top + plotHeight);
    context.lineTo(coordinates[0].x, padding.top + plotHeight);
    context.closePath();
    context.fillStyle = "rgba(101, 181, 255, 0.18)";
    context.fill();

    context.beginPath();
    coordinates.forEach((point, index) => {
        index ? context.lineTo(point.x, point.y) : context.moveTo(point.x, point.y);
    });
    context.strokeStyle = "#65b5ff";
    context.lineWidth = 3;
    context.stroke();
    context.fillStyle = "#cce7ff";
    coordinates.forEach((point) => {
        context.beginPath();
        context.arc(point.x, point.y, 4, 0, Math.PI * 2);
        context.fill();
    });

    context.fillStyle = "#9fb5d7";
    context.font = "12px Arial";
    context.textAlign = "center";
    const labelIndexes = [...new Set([0, Math.floor((points.length - 1) / 2), points.length - 1])];
    labelIndexes.forEach((index) => {
        context.fillText(points[index].label, coordinates[index].x, height - 14);
    });
}

function drawEventFrequency() {
    const canvas = document.getElementById("eventFrequencyChart");
    const { context, width, height } = prepareCanvas(canvas);
    const labels = Object.keys(analyticsData.event_counts);
    const values = Object.values(analyticsData.event_counts);
    const maxValue = Math.max(...values, 0);
    const padding = { top: 20, right: 20, bottom: 64, left: 38 };
    const plotWidth = width - padding.left - padding.right;
    const plotHeight = height - padding.top - padding.bottom;

    if (maxValue === 0) {
        drawEmptyState(context, width, height, "No suspicious events were recorded.");
        return;
    }

    context.strokeStyle = "rgba(147, 185, 255, 0.18)";
    context.fillStyle = "#9fb5d7";
    context.font = "12px Arial";
    context.textAlign = "right";
    for (let value = 0; value <= maxValue; value += 1) {
        const y = padding.top + plotHeight * (1 - value / maxValue);
        context.beginPath();
        context.moveTo(padding.left, y);
        context.lineTo(width - padding.right, y);
        context.stroke();
        context.fillText(value, padding.left - 8, y + 4);
    }

    const slotWidth = plotWidth / labels.length;
    const barWidth = Math.min(54, slotWidth * 0.58);
    labels.forEach((label, index) => {
        const barHeight = (values[index] / maxValue) * plotHeight;
        const x = padding.left + index * slotWidth + (slotWidth - barWidth) / 2;
        const y = padding.top + plotHeight - barHeight;
        context.fillStyle = palette[index];
        context.fillRect(x, y, barWidth, barHeight);
        context.fillStyle = "#edf5ff";
        context.textAlign = "center";
        context.fillText(values[index], x + barWidth / 2, y - 8);
        context.save();
        context.translate(x + barWidth / 2, height - 16);
        context.rotate(-0.5);
        context.fillStyle = "#9fb5d7";
        context.fillText(label, 0, 0);
        context.restore();
    });
}

function buildHeatmap() {
    const types = {
        tab_switch: "Tab switch",
        window_focus_lost: "Focus lost",
        no_face: "Face absent",
        multiple_faces: "Multiple faces",
    };
    const counts = {};
    analyticsData.events.forEach((event) => {
        if (!types[event.event_type]) return;
        const time = new Date(event.event_timestamp);
        const minute = String(Math.floor(time.getMinutes() / 15) * 15).padStart(2, "0");
        const interval = `${String(time.getHours()).padStart(2, "0")}:${minute}`;
        const key = `${interval}|${event.event_type}`;
        counts[key] = (counts[key] || 0) + 1;
    });

    const container = document.getElementById("eventHeatmap");
    const intervals = [...new Set(Object.keys(counts).map((key) => key.split("|")[0]))].sort();
    if (!intervals.length) {
        container.textContent = "No suspicious events were recorded for this session.";
        return;
    }

    const table = document.createElement("table");
    const header = table.insertRow();
    header.insertCell().textContent = "Time";
    Object.values(types).forEach((label) => { header.insertCell().textContent = label; });
    intervals.forEach((interval) => {
        const row = table.insertRow();
        row.insertCell().textContent = interval;
        Object.keys(types).forEach((type) => {
            const count = counts[`${interval}|${type}`] || 0;
            const cell = row.insertCell();
            cell.textContent = count;
            cell.style.backgroundColor = count
                ? `rgba(244, 183, 76, ${Math.min(0.22 + count * 0.16, 0.85)})`
                : "rgba(147, 185, 255, 0.06)";
        });
    });
    container.replaceChildren(table);
}

function renderAnalytics() {
    drawScoreTrend();
    drawEventFrequency();
    buildHeatmap();
}

renderAnalytics();
window.addEventListener("resize", () => {
    window.clearTimeout(window.analyticsResizeTimer);
    window.analyticsResizeTimer = window.setTimeout(() => {
        drawScoreTrend();
        drawEventFrequency();
    }, 120);
});
