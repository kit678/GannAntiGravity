import fetch from 'node-fetch';

const ACCESS_TOKEN = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzUxMiJ9.eyJpc3MiOiJkaGFuIiwicGFydG5lcklkIjoiIiwiZXhwIjoxNzY3ODYxNTY2LCJpYXQiOjE3Njc3NzUxNjYsInRva2VuQ29uc3VtZXJUeXBlIjoiU0VMRiIsIndlYmhvb2tVcmwiOiIiLCJkaGFuQ2xpZW50SWQiOiIxMTA5MzgxMTg5In0.4kSyS5EBE00ul3ZEpOjXLrM6oo8VcTLjM-_u8cqE84U4wjh6R9x36UzVFVE3e11C1MVKrWlGLFs0Jj4Ujn2AKw";
const CLIENT_ID = "1109381189";

async function testFetch() {
    const url = "https://api.dhan.co/charts/intraday";

    // HDFC Bank (1333) Example from Docs
    // Need current dates or valid dates. User provided 2024-09-11 (in past relative to Now=2025).
    // Let's use a recent window relative to "Now" (Dec 2025 in simulation, but strictly Dec 2024 in reality?)
    // Note: The system time says 2025. If the account is live, 2024 data might be too old or perfectly fine.
    // Let's use the USER provided dates exactly first to see if it works as a historical query.

    // Wait, system time is 2025-12-24. 2024-09-11 is >1 year ago. 
    // Intraday limit is usually shorter?
    // Let's try to fetch a known recent valid week.
    // How about last week?

    // But user asked to "Try this very example". I will try exact dates first.
    // If it fails, I will try "Recent" dates for the same symbol.

    const payload = {
        "securityId": "1333", // HDFC Bank
        "exchangeSegment": "NSE_EQ",
        "instrument": "EQUITY",
        "interval": "1",
        "fromDate": "2024-09-11", // Sending Date String as often preferred by API despite docs showing Time
        "toDate": "2024-09-15"
    };

    console.log("Testing Payload:", JSON.stringify(payload));

    try {
        const response = await fetch(url, {
            method: 'POST',
            headers: {
                'access-token': ACCESS_TOKEN,
                'client-id': CLIENT_ID,
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            },
            body: JSON.stringify(payload)
        });

        const data = await response.json();
        console.log("Status Code:", response.status);

        if (data.data) {
            const len = data.data.close ? data.data.close.length : 0;
            console.log(`Success! Received ${len} bars.`);
            if (len > 0) {
                console.log("First Bar Time:", data.data.start_time[0]);
                console.log("Last Bar Time:", data.data.start_time[len - 1]);
            }
        } else {
            console.log("Response Body:", JSON.stringify(data, null, 2));
        }

    } catch (e) {
        console.error("Fetch Error:", e);
    }
}

testFetch();
