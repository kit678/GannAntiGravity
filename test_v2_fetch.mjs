import fetch from 'node-fetch';

const ACCESS_TOKEN = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzUxMiJ9.eyJpc3MiOiJkaGFuIiwicGFydG5lcklkIjoiIiwiZXhwIjoxNzY4MzIxMzM4LCJpYXQiOjE3NjgyMzQ5MzgsInRva2VuQ29uc3VtZXJUeXBlIjoiU0VMRiIsIndlYmhvb2tVcmwiOiIiLCJkaGFuQ2xpZW50SWQiOiIxMTA5MzgxMTg5In0.s_Kw_zE3H7Jy_Q5dv29CXWAmGQcyx9tX7xot3kZayVzQplgkkRw9GF-QYLLxFCgsgvsYmlQAQ6W4bYcZUsOjvg";

async function testFetch() {
    // IMPORTANT: Documentation says "https://api.dhan.co/v2/charts/intraday"
    // My previous attempts used "https://api.dhan.co/charts/intraday" (No v2)
    const url = "https://api.dhan.co/v2/charts/intraday";

    // Dates from text: "2023-09-11 09:30:00" to "2023-09-15 13:00:00"
    // Using HDFC Bank (1333) as per example
    const payload = {
        "securityId": "1333",
        "exchangeSegment": "NSE_EQ",
        "instrument": "EQUITY",
        "interval": "1",
        "oi": false,
        "fromDate": "2023-09-11 09:30:00",
        "toDate": "2023-09-15 13:00:00"
    };

    console.log("Testing URL:", url);
    console.log("Payload:", JSON.stringify(payload));

    try {
        const response = await fetch(url, {
            method: 'POST',
            headers: {
                'access-token': ACCESS_TOKEN,
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            },
            body: JSON.stringify(payload)
        });

        if (!response.ok) {
            console.log("HTTP Error:", response.status, response.statusText);
            const text = await response.text();
            console.log("Error Body:", text);
            return;
        }

        const data = await response.json();

        // Inspect Response Structure - API V2 might return flat structure or different wrapper
        const target = data.data || data; // fallback

        if (target && target.timestamp) { // Note: Found 'timestamp' in previous run
            const len = target.timestamp.length;
            console.log(`Success! Received ${len} bars.`);

            // Check Dates
            console.log("First Bar:", target.timestamp[0]);
            console.log("Last Bar:", target.timestamp[len - 1]);

            // Convert to check year
            // Dhan usually returns unix (seconds)
            const firstDate = new Date(target.timestamp[0] * 1000);
            console.log("First Date Converted:", firstDate.toString());
        } else {
            console.log("Check keys:", Object.keys(target));
        }

    } catch (e) {
        console.error("Fetch Error:", e);
    }
}

testFetch();
