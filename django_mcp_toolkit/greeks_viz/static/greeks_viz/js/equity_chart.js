document.addEventListener("DOMContentLoaded", function() {
    const dataStr = document.getElementById('ohlcv-data').textContent;
    const data = JSON.parse(JSON.parse(dataStr)); // Double parse needed as it's serialized as string

    var trace = {
        x: data.dates,
        close: data.close,
        decreasing: {line: {color: '#EF5350'}},
        high: data.high,
        increasing: {line: {color: '#26A69A'}},
        line: {color: 'rgba(31,119,180,1)'},
        low: data.low,
        open: data.open,
        type: 'candlestick',
        xaxis: 'x',
        yaxis: 'y'
    };

    var layout = {
        dragmode: 'zoom',
        margin: { r: 10, t: 25, b: 40, l: 60 },
        showlegend: false,
        xaxis: {
            autorange: true,
            domain: [0, 1],
            range: [data.dates[0], data.dates[data.dates.length - 1]],
            rangeslider: {range: [data.dates[0], data.dates[data.dates.length - 1]]},
            title: 'Date',
            type: 'date'
        },
        yaxis: {
            autorange: true,
            domain: [0, 1],
            type: 'linear'
        }
    };

    Plotly.newPlot('equity-chart', [trace], layout);
});
