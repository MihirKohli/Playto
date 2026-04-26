import React, { useState } from "react";

function App() {
  const [response, setResponse] = useState(null);

  // Example API calls (replace with your real endpoints)
  const fetchData = async (type) => {
    let url = "";

    if (type === "balance") url = "http://127.0.0.1:8000/api/v1/dashboard";
    if (type === "payouts") url = "http://127.0.0.1:8000/api/v1/merchants";

    try {
      const res = await fetch(url);
      const data = await res.json();
      setResponse(data);
    } catch (err) {
      setResponse({ error: "Failed to fetch" });
    }
  };

  return (
    <div style={{ padding: "20px" }}>
      <h1>API Tester</h1>

      {/* Buttons */}
      <div style={{ display: "flex", gap: "10px" }}>
        <button onClick={() => fetchData("balance")}>
          Get Balance
        </button>

        <button onClick={() => fetchData("payouts")}>
          Get Payouts
        </button>

        <button onClick={() => fetchData("balance")}>
          Refresh
        </button>

        <button onClick={() => setResponse(null)}>
          Clear
        </button>
      </div>

      {/* Response Display */}
      <div style={{ marginTop: "20px" }}>
        <h2>Response:</h2>

        {response ? (
          <pre
            style={{
              background: "#f4f4f4",
              padding: "10px",
              borderRadius: "5px",
            }}
          >
            {JSON.stringify(response, null, 2)}
          </pre>
        ) : (
          <p>No data</p>
        )}
      </div>
    </div>
  );
}

export default App;