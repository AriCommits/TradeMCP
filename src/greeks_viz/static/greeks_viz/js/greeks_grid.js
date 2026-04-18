document.addEventListener("DOMContentLoaded", function() {
    const dataStr = document.getElementById('greeks-data').textContent;
    const greeksData = JSON.parse(dataStr);

    greeksData.forEach((item, index) => {
        let surfaceData = item.surface;
        let trace = {
            z: surfaceData.z,
            x: surfaceData.x,
            y: surfaceData.y,
            type: 'surface',
            colorscale: 'Viridis'
        };

        let layout = {
            title: item.greeks.join(' · ').toUpperCase(),
            margin: { l: 0, r: 0, b: 0, t: 30 },
            scene: {
                xaxis: { title: 'Strike' },
                yaxis: { title: 'DTE' },
                zaxis: { title: 'Value' }
            }
        };

        Plotly.newPlot('surface-' + index, [trace], layout);
    });
});
