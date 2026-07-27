export default async ({ page, context }) => {
  const BASE_URL = "https://business.tankarta.cz";
  const LOGIN_URL = `${BASE_URL}/Login?ReturnUrl=%2F`;
  const LIST_PRICE_URL = `${BASE_URL}/Dashboard-ListPrice`;
  const timeoutMs = Math.max(10000, Number(context.timeoutMs || 90000));
  const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

  page.setDefaultTimeout(timeoutMs);
  page.setDefaultNavigationTimeout(timeoutMs);

  const capturedHeaders = {};
  page.on("request", (request) => {
    const url = request.url();
    if (!url.startsWith(BASE_URL)) return;
    const headers = request.headers();
    for (const [name, value] of Object.entries(headers)) {
      const lower = name.toLowerCase();
      if (
        lower === "authorization" ||
        lower.startsWith("x-") ||
        lower === "csrf-token" ||
        lower === "requestverificationtoken"
      ) {
        capturedHeaders[lower] = value;
      }
    }
  });

  async function isVisible(element) {
    if (!element) return false;
    return element.evaluate((node) => {
      const style = window.getComputedStyle(node);
      const rect = node.getBoundingClientRect();
      return (
        style.visibility !== "hidden" &&
        style.display !== "none" &&
        rect.width > 0 &&
        rect.height > 0
      );
    });
  }

  async function firstVisible(selectors) {
    for (const selector of selectors) {
      const element = await page.$(selector);
      if (element && (await isVisible(element))) return element;
    }
    return null;
  }

  async function waitForVisible(selectors, maximumMs = timeoutMs) {
    const deadline = Date.now() + maximumMs;
    while (Date.now() < deadline) {
      const element = await firstVisible(selectors);
      if (element) return element;
      await delay(250);
    }
    return null;
  }

  async function buttonByText(pattern) {
    const elements = await page.$$("button, input[type='submit'], a[role='button']");
    for (const element of elements) {
      if (!(await isVisible(element))) continue;
      const text = await element.evaluate((node) =>
        String(node.innerText || node.value || node.textContent || "").trim()
      );
      if (pattern.test(text)) return element;
    }
    return null;
  }

  async function typeInto(element, value) {
    await element.click({ clickCount: 3 });
    await page.keyboard.press("Backspace");
    await element.type(String(value), { delay: 15 });
  }

  async function clearBrowserState() {
    try {
      const client = await page.target().createCDPSession();
      await client.send("Network.clearBrowserCookies");
      await client.detach();
    } catch (_) {}
    await page.goto(LOGIN_URL, { waitUntil: "domcontentloaded", timeout: timeoutMs });
    try {
      await page.evaluate(() => {
        localStorage.clear();
        sessionStorage.clear();
      });
    } catch (_) {}
  }

  async function restoreSession() {
    const saved = context.session || {};
    if (Array.isArray(saved.cookies) && saved.cookies.length) {
      try {
        await page.setCookie(...saved.cookies);
      } catch (_) {}
    }
    await page.goto(BASE_URL, { waitUntil: "domcontentloaded", timeout: timeoutMs });
    if (saved.localStorage || saved.sessionStorage) {
      try {
        await page.evaluate((state) => {
          localStorage.clear();
          sessionStorage.clear();
          for (const [key, value] of Object.entries(state.localStorage || {})) {
            localStorage.setItem(key, value);
          }
          for (const [key, value] of Object.entries(state.sessionStorage || {})) {
            sessionStorage.setItem(key, value);
          }
        }, saved);
      } catch (_) {}
      await page.reload({ waitUntil: "domcontentloaded", timeout: timeoutMs });
    }
  }

  const usernameSelectors = [
    "input[name='Username']",
    "input[name='UserName']",
    "input[name='Login']",
    "input[name='Email']",
    "input[id='Username']",
    "input[id='UserName']",
    "input[id='Login']",
    "input[id='Email']",
    "input[name*='user' i]",
    "input[name*='login' i]",
    "input[name*='email' i]",
    "input[id*='user' i]",
    "input[id*='login' i]",
    "input[id*='email' i]",
    "input[autocomplete='username']",
    "input[type='email']",
    "input[type='text']",
  ];
  const passwordSelectors = [
    "input[name='Password']",
    "input[id='Password']",
    "input[name*='password' i]",
    "input[id*='password' i]",
    "input[autocomplete='current-password']",
    "input[type='password']",
  ];
  const otpSelectors = [
    "input[autocomplete='one-time-code']",
    "input[name*='otp' i]",
    "input[name*='code' i]",
    "input[id*='otp' i]",
    "input[id*='code' i]",
    "input[inputmode='numeric']",
  ];

  async function loginFresh() {
    await clearBrowserState();
    const username = await waitForVisible(usernameSelectors, timeoutMs);
    const password = await waitForVisible(passwordSelectors, timeoutMs);
    if (!username || !password) {
      const error = new Error("Tankarta login fields were not found");
      error.code = "login_form_changed";
      throw error;
    }

    await typeInto(username, context.username);
    await typeInto(password, context.password);

    let submit = await firstVisible(["button[type='submit']", "input[type='submit']"]);
    if (!submit) submit = await buttonByText(/p(?:r|ř)ihl[aá]sit|login|sign in|pokra[cč]ovat/i);

    const navigation = page
      .waitForNavigation({ waitUntil: "domcontentloaded", timeout: timeoutMs })
      .catch(() => null);
    if (submit) await submit.click();
    else await page.keyboard.press("Enter");
    await Promise.race([navigation, delay(5000)]);

    const otp = await firstVisible(otpSelectors);
    if (otp) {
      const error = new Error("Tankarta account requires two-factor authentication");
      error.code = "two_factor_required";
      throw error;
    }
  }

  async function collectHeaders() {
    const headers = { ...capturedHeaders };
    headers.accept = "application/json, text/plain, */*";
    try {
      const cookies = await page.cookies(BASE_URL);
      for (const cookie of cookies) {
        const name = String(cookie.name || "").toLowerCase();
        const value = decodeURIComponent(String(cookie.value || ""));
        if (name === "xsrf-token" && !headers["x-xsrf-token"]) {
          headers["x-xsrf-token"] = value;
        }
        if (name === "csrf-token" && !headers["x-csrf-token"]) {
          headers["x-csrf-token"] = value;
        }
      }
    } catch (_) {}
    return headers;
  }

  async function fetchPrices() {
    const headers = await collectHeaders();
    const response = await page.evaluate(
      async ({ url, headers, timeoutMs }) => {
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), timeoutMs);
        try {
          const result = await fetch(url, {
            method: "GET",
            headers,
            credentials: "include",
            cache: "no-store",
            redirect: "follow",
            signal: controller.signal,
          });
          return {
            status: result.status,
            url: result.url,
            contentType: result.headers.get("content-type") || "",
            text: await result.text(),
          };
        } finally {
          clearTimeout(timer);
        }
      },
      { url: LIST_PRICE_URL, headers, timeoutMs }
    );

    if (
      response.status === 401 ||
      response.status === 403 ||
      /\/login(?:\?|$)/i.test(response.url)
    ) {
      const error = new Error("Tankarta session is not authenticated");
      error.code = "authentication_failed";
      throw error;
    }
    if (response.status < 200 || response.status >= 300) {
      const error = new Error(`Tankarta list-price endpoint returned HTTP ${response.status}`);
      error.code = "api_error";
      throw error;
    }

    let decoded;
    try {
      decoded = JSON.parse(response.text);
    } catch (_) {
      const error = new Error("Tankarta list-price response was not JSON");
      error.code = /text\/html/i.test(response.contentType)
        ? "authentication_failed"
        : "invalid_payload";
      throw error;
    }

    const array = Array.isArray(decoded)
      ? decoded
      : decoded && Array.isArray(decoded.data)
        ? decoded.data
        : null;
    if (!array) {
      const error = new Error("Tankarta list-price JSON was not an array");
      error.code = "invalid_payload";
      throw error;
    }

    // Return only fields required by the integration. divisionID is retained
    // transiently so duplicate product names can be distinguished, then hashed
    // by Python and never persisted or exposed by an entity.
    return array.map((item) => ({
      divisionID: item ? item.divisionID : null,
      product: item ? item.product : null,
      productPrice: item ? item.productPrice : null,
    }));
  }

  async function saveSession() {
    let cookies = [];
    let storage = { localStorage: {}, sessionStorage: {} };
    try {
      cookies = (await page.cookies(BASE_URL)).map((cookie) => {
        const saved = {
          name: cookie.name,
          value: cookie.value,
          domain: cookie.domain,
          path: cookie.path,
          expires: cookie.expires,
          httpOnly: cookie.httpOnly,
          secure: cookie.secure,
        };
        if (cookie.sameSite) saved.sameSite = cookie.sameSite;
        return saved;
      });
    } catch (_) {}
    try {
      storage = await page.evaluate(() => ({
        localStorage: Object.fromEntries(Object.entries(localStorage)),
        sessionStorage: Object.fromEntries(Object.entries(sessionStorage)),
      }));
    } catch (_) {}
    return { cookies, ...storage };
  }

  try {
    await restoreSession();
    await delay(1500);
    let prices;
    try {
      prices = await fetchPrices();
    } catch (error) {
      if (error.code !== "authentication_failed") throw error;
      for (const key of Object.keys(capturedHeaders)) delete capturedHeaders[key];
      await loginFresh();
      await delay(1500);
      try {
        prices = await fetchPrices();
      } catch (secondError) {
        if (secondError.code === "authentication_failed") {
          const authError = new Error("Tankarta username or password was rejected");
          authError.code = "authentication_failed";
          throw authError;
        }
        throw secondError;
      }
    }

    return {
      data: {
        success: true,
        prices,
        session: await saveSession(),
      },
      type: "application/json",
    };
  } catch (error) {
    return {
      data: {
        success: false,
        code: error.code || "unknown",
        error: error.message || String(error),
      },
      type: "application/json",
    };
  }
};
