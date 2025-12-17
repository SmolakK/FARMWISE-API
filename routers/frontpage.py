from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from fastapi import Depends
from security import get_current_active_user
from schemas import User
from mappings.data_source_mapping import API_PATH_RANGES
from utils.country_bboxes import return_country_bboxes

available_countries = list(return_country_bboxes().keys())
available_factors = []
for x in API_PATH_RANGES.values():
    available_factors += x[2]
available_factors = list(set(available_factors))

frontpage_router = APIRouter()


@frontpage_router.get("/", response_class=HTMLResponse)
async def login_page():
    html_content = """
    <html>
        <head>
            <title>FARMWISE API Login</title>
            <style>
                body {
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    height: 100vh;
                    background-color: #f5f5f5;
                    font-family: Arial, sans-serif;
                }
                form {
                    background-color: #fff;
                    padding: 20px;
                    border-radius: 10px;
                    box-shadow: 0 0 10px rgba(0, 0, 0, 0.1);
                    width: 300px;
                }
                label {
                    display: block;
                    margin-top: 10px;
                    font-weight: bold;
                }
                input[type="text"], input[type="password"], input[type="submit"] {
                    width: 100%;
                    margin-top: 5px;
                    padding: 5px;
                }
                .error {
                    color: red;
                    margin-top: 10px;
                }
            </style>
            <script>
                async function login(event) {
                    event.preventDefault();

                    const username = document.getElementById('username').value;
                    const password = document.getElementById('password').value;

                    const formData = new URLSearchParams();
                    formData.append('username', username);
                    formData.append('password', password);

                    const response = await fetch('/token', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/x-www-form-urlencoded'
                        },
                        body: formData
                    });

                    if (response.ok) {
                        const data = await response.json();
                        localStorage.setItem('auth_token', data.access_token);
                        window.location.href = '/frontend';
                    } else {
                        document.getElementById('error').innerText = 'Invalid username or password.';
                    }
                }
            </script>
        </head>
        <body>
            <form onsubmit="login(event)">
                <h2 style="text-align:center;">FARMWISE API Login</h2>
                <label for="username">Username:</label>
                <input type="text" id="username" name="username" required>

                <label for="password">Password:</label>
                <input type="password" id="password" name="password" required>

                <input type="submit" value="Login">

                <div id="error" class="error"></div>
            </form>
        </body>
    </html>
    """
    return HTMLResponse(content=html_content)


@frontpage_router.get("/frontend", response_class=HTMLResponse)
async def secured_frontend_page():
    return HTMLResponse("""
<html>
    <head>
        <title>API Page</title>
        <link rel="stylesheet" type="text/css" href="/static/style.css">
        <script>
            async function loadPage() {
                const token = localStorage.getItem('auth_token');
                if (!token) {
                    alert('You must log in first.');
                    window.location.href = '/';
                    return;
                }
                console.log('Fetching /api-call...');

                const userResponse = await fetch('/users/me', {
                    headers: { 'Authorization': 'Bearer ' + token }
                });

                if (!userResponse.ok) {
                    alert('Session expired or invalid token.');
                    localStorage.removeItem('auth_token');
                    window.location.href = '/';
                    return;
                }

                const response = await fetch('/api-call', {
                    headers: { 'Authorization': 'Bearer ' + token }
                });
                console.log('Fetch response:', response);

                if (response.ok) {
                    const html = await response.text();
                    document.getElementById('app').innerHTML = html;

                    console.log('API form injected');

                    document.getElementById('apiForm').addEventListener('submit', submitForm);

                    document.getElementById('use_country').addEventListener('click', toggleInputs);
                    document.getElementById('use_bbox').addEventListener('click', toggleInputs);
                } else {
                    document.getElementById('app').innerHTML = '<p>Error loading the API call page.</p>';
                }
            }

            function toggleInputs() {
                var useCountry = document.getElementById("use_country").checked;
                console.log("Use country:", useCountry);
                document.getElementById("country_select").disabled = !useCountry;
            
                document.getElementById("bbox_n").disabled = useCountry;
                document.getElementById("bbox_s").disabled = useCountry;
                document.getElementById("bbox_e").disabled = useCountry;
                document.getElementById("bbox_w").disabled = useCountry;
            }

            async function submitForm(event) {
                event.preventDefault();
                
                document.getElementById('result').innerText = 'Submitted';

                console.log('submitForm triggered');

                const token = localStorage.getItem('auth_token');
                if (!token) {
                    alert('Token missing. Please log in again.');
                    window.location.href = '/';
                    return;
                }

                var useCountry = document.getElementById("use_country").checked;
                var countries = Array.from(document.getElementById("country_select").selectedOptions).map(option => option.value);
                var factors = Array.from(document.getElementById("factors").selectedOptions).map(option => option.value);

                var payload = {
                    level: parseInt(document.getElementById("s2_level").value),
                    time_from: document.getElementById("from").value,
                    time_to: document.getElementById("to").value,
                    factors: factors,
                    separate_api: document.getElementById("separate_api").checked,
                    interpolation: !document.getElementById("no_interpolation").checked,
                    produce_map: document.getElementById("produce_map").checked
                };

                if (useCountry) {
                    payload['country'] = countries;
                } else {
                    payload['bounding_box'] = [
                        parseFloat(document.getElementById("bbox_n").value),
                        parseFloat(document.getElementById("bbox_s").value),
                        parseFloat(document.getElementById("bbox_e").value),
                        parseFloat(document.getElementById("bbox_w").value)
                    ];
                }

                const response = await fetch('/read-data', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': 'Bearer ' + token
                    },
                    body: JSON.stringify(payload)
                });

                if (!response.ok) {
                    document.getElementById('result').innerText = 'Error: ' + response.statusText;
                    return;
                }

                const reader = response.body.getReader();
                const decoder = new TextDecoder();
                let resultText = '';

                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;
                    resultText += decoder.decode(value);
                    document.getElementById('result').innerText = resultText;
                }
            }

            function logout() {
                localStorage.removeItem('auth_token');
                window.location.href = '/';
            }

            window.onload = loadPage;
        </script>
    </head>
    <body>
    
        <div id="app">Loading...</div>
        <button onclick="logout()" style="position: fixed; top: 5px; right: 10px;">Logout</button>
    </body>
</html>
    """)


@frontpage_router.get("/api-call", response_class=HTMLResponse)
async def api_call_page(current_user: User = Depends(get_current_active_user)):
    country_options = "".join([f'<option value="{c}">{c}</option>' for c in available_countries])
    factor_options = "".join([f'<option value="{f}">{f}</option>' for f in available_factors])

    html_content = f"""
    <html>
    <head>
        <style>
                           .about-container {{
                position: fixed;
                top: 12px;
                left: 12px;
                z-index: 1000;
                font-family: Arial, sans-serif;
            }}
            
            .about-icon {{
                background: #ffffff;
                border: 1px solid #ccc;
                border-radius: 20px;
                padding: 6px 12px;
                font-size: 13px;
                cursor: help;
                box-shadow: 0 2px 6px rgba(0,0,0,0.15);
            }}
            
            .about-tooltip {{
                display: none;
                position: absolute;
                top: 38px;
                left: 0;
                width: 320px;
                background: #ffffff;
                border-radius: 8px;
                padding: 14px;
                font-size: 13px;
                line-height: 1.45;
                box-shadow: 0 4px 14px rgba(0,0,0,0.2);
            }}
            
            .about-icon:hover + .about-tooltip {{
    display: block;
            }}
                    .logo-container {{
            position: fixed;
            top: 12px;
            z-index: 1000;
        }}
        
        .logo-container.left {{
            left: 40px;
        }}
        
        .logo-container.right {{
            right: 40px;
        }}
        
        .logo-container img {{
            height: 102px;   /* keep both logos visually balanced */
            width: auto;
            opacity: 0.9;
        }}


            body {{
                font-family: Arial, sans-serif;
                background-color: #f5f5f5;
                margin: 0;
                padding: 0;
                display: flex;
                justify-content: center;
                align-items: flex-start;
                min-height: 100vh;
            }}
            form {{
                background: #fff;
                padding: 20px;
                margin: 20px;
                border-radius: 10px;
                box-shadow: 0 0 10px rgba(0,0,0,0.1);
                max-width: 600px;
                width: 100%;
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 20px;
            }}
            h2 {{
                grid-column: span 2;
                text-align: center;
            }}
            label {{
                font-weight: bold;
                display: block;
                margin-bottom: 4px;
            }}
            select, input[type="text"], input[type="number"], input[type="submit"], input[type="button"] {{
                width: 100%;
                padding: 6px;
                margin-top: 2px;
                border: 1px solid #ccc;
                border-radius: 4px;
                box-sizing: border-box;
            }}
            .bbox-container {{
                display: flex;
                flex-wrap: wrap;
                gap: 8px;
            }}
            .bbox-container label {{
                flex: 1 1 45%;
            }}
            .time-container {{
                display: flex;
                flex-direction: column;
                gap: 12px;
            }}
            .buttons {{
                grid-column: span 2;
                display: flex;
                gap: 12px;
                justify-content: center;
            }}
            pre {{
                grid-column: span 2;
                background: #f0f0f0;
                padding: 10px;
                border-radius: 6px;
                overflow-x: auto;
            }}
            /* Make it stack on small screens */
            @media (max-width: 700px) {{
                form {{
                    grid-template-columns: 1fr;
                }}
                .buttons {{
                    flex-direction: column;
                }}
            }}
        </style>
    </head>
    <body>
    <div class="logo-container left">
        <img src="/static/upwr.png" alt="UPWr logo">
    </div>
    
    <div class="logo-container right">
        <img src="/static/farmwise_logo.png" alt="FARMWISE logo">
    </div>

        <div class="about-container">
            <span class="about-icon">About ⓘ</span>
            <div class="about-tooltip">
                <strong>FARMWISE API</strong><br><br>
        
                This interface allows you to query spatio-temporal
                environmental and agricultural indicators derived
                from multiple data sources.<br><br>
        
                You can:
                <ul style="padding-left: 18px; margin: 6px 0;">
                    <li>Select data by country or custom bounding box</li>
                    <li>Define time ranges and spatial resolution (S2)</li>
                    <li>Choose multiple parameters</li>
                    <li>Generate interactive maps</li>
                </ul>
        
                All requests are processed on demand and require authentication.
                
                            This API was created thanks to the project funded from the European Union’s Horizon Europe research and innovation programme under GA Nº 101135533.
                    Authors: Kamil Smolak, Jakub Misiewicz, Wiesław Fiałkiewicz, Arkadiusz Głogowski, Marc Laurencelle, Damien Rambourg.
            </div>
        </div>

    <form id="apiForm" action="javascript:void(0);">
        <h2>FARMWISE API</h2>

        <!-- Location mode -->
        <div style="grid-column: span 2; display: flex; flex-direction: column; gap: 6px;">
        
            <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
                <input type="radio" id="use_country" name="location_mode" value="country" checked>
                <label for="use_country">Select by Country</label>
                <span style="font-size: 0.85em; color: #555;">
                    (Data will be generated based on the bounding box defined by the most distant points of selected countries)
                </span>
            </div>
        
            <div style="display: flex; align-items: center; gap: 8px;">
                <input type="radio" id="use_bbox" name="location_mode" value="bbox">
                <label for="use_bbox">Select by Bounding Box</label>
            </div>
        
        </div>


        <!-- Country selection -->
        <div>
            <label for="country_select">Select countries:</label>
            <select id="country_select" name="country" multiple size="6">
                {country_options}
            </select>
        </div>

        <!-- Factors selection -->
        <div>
            <label for="factors">Select Parameters:</label>
            <select id="factors" name="factors" multiple size="6">
                {factor_options}
            </select>
        </div>

        <!-- Bounding box input -->
        <div style="grid-column: span 2;">
            <label>Bounding Box (N, S, E, W):</label>
            <div class="bbox-container">
                <label>N: <input type="text" id="bbox_n" name="bbox_n" disabled></label>
                <label>S: <input type="text" id="bbox_s" name="bbox_s" disabled></label>
                <label>E: <input type="text" id="bbox_e" name="bbox_e" disabled></label>
                <label>W: <input type="text" id="bbox_w" name="bbox_w" disabled></label>
            </div>
                <small class="bbox-description" style="display:block; margin-top:4px; color:#666;">
        Coordinates should be entered in decimal degrees (WGS 84).<br>
        N = northernmost latitude, S = southernmost latitude,<br>
        E = easternmost longitude, W = westernmost longitude.<br>
        Example: N=51.15, S=50.80, E=17.20, W=16.80 (Wrocław, Poland area).
                </small>
        </div>

        <!-- Time selection -->
        <div class="time-container">
            <label for="from">From (YYYY-MM-DD):</label>
            <input type="text" id="from" name="time_from" value="2017-01-10">
        </div>
        <div class="time-container">
            <label for="to">To (YYYY-MM-DD):</label>
            <input type="text" id="to" name="time_to" value="2017-01-12">
        </div>

        <!-- S2 Level selection -->
        <div style="grid-column: span 2;">
            <label for="s2_level">
                S2 Level (geographic resolution)
                <a href="http://s2geometry.io/resources/s2cell_statistics.html" target="_blank">[?]</a>
            </label>
            <input type="number" id="s2_level" name="s2_level" min="2" max="14" value="10">
        </div>
        
        <div style="grid-column: span 2; display: flex; flex-direction: column; gap: 6px;">
        <label>
            <input type="checkbox" id="separate_api" name="separate_api">
            Produce APIs outputs separately (in separate columns)
        </label>
        <label>
            <input type="checkbox" id="produce_map" name="produce_map">
            Produce an interactive map
        </label>
        <label>
            <input type="checkbox" id="no_interpolation" name="no_interpolation" checked>
            Do not interpolate data for visualization (faster response)
        </label>
    </div>

        <!-- Buttons -->
        <div class="buttons">
            <input type="submit" value="Submit to FARMWISE API">
            <input type="button" value="Logout" onclick="logout()">
        </div>

        <pre id="result">Here you will find submit confirmation or error message in case of failure.</pre>
    </form>
    </body>
    </html>
    """

    return HTMLResponse(content=html_content)

