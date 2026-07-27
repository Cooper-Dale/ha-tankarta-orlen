export default async ({ page, context }) => {
  const BASE_URL = "https://business.tankarta.cz";
  const LOGIN_URL = `${BASE_URL}/Login?ReturnUrl=%2F`;
  const timeoutMs = Math.max(10000, Number(context.timeoutMs || 90000));
  const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

  let stage = "browserless_started";
  let lastHttpStatus = null;
  let lastResponseUrl = null;
  let lastContentType = null;
  let loginPostObserved = false;

  page.setDefaultTimeout(timeoutMs);
  page.setDefaultNavigationTimeout(timeoutMs);

  let listPricePostObserved = false;
  let listPriceRequestBodyLength = null;
  let listPriceRequestContentType = null;
  let listPriceCapturePromise = null;

  function isListPriceUrl(rawUrl) {
    try {
      const parsed = new URL(String(rawUrl || ""), BASE_URL);
      return parsed.origin === BASE_URL && parsed.pathname === "/Dashboard-ListPrice";
    } catch (_) {
      return false;
    }
  }

  page.on("request", (request) => {
    const url = request.url();
    if (!url.startsWith(BASE_URL)) return;

    const method = request.method().toUpperCase();
    if (method === "POST" && /\/Login(?:\?|$)/i.test(url)) {
      loginPostObserved = true;
    }

    if (method === "POST" && isListPriceUrl(url)) {
      listPricePostObserved = true;
      const postData = request.postData();
      listPriceRequestBodyLength = postData === null ? null : String(postData).length;
      listPriceRequestContentType = request.headers()["content-type"] || null;
    }
  });

  page.on("response", (response) => {
    const request = response.request();
    if (request.method().toUpperCase() !== "POST" || !isListPriceUrl(response.url())) {
      return;
    }

    listPricePostObserved = true;
    listPriceCapturePromise = (async () => ({
      status: response.status(),
      url: response.url(),
      contentType: response.headers()["content-type"] || "",
      text: await response.text(),
    }))();
  });

  function resetListPriceCapture() {
    listPricePostObserved = false;
    listPriceRequestBodyLength = null;
    listPriceRequestContentType = null;
    listPriceCapturePromise = null;
  }

  function safeUrl(rawUrl) {
    try {
      const parsed = new URL(String(rawUrl || ""), BASE_URL);
      return `${parsed.origin}${parsed.pathname}`;
    } catch (_) {
      return "unknown";
    }
  }

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
  const challengeSelectors = [
    "iframe[src*='captcha' i]",
    "iframe[title*='captcha' i]",
    ".g-recaptcha",
    "[class*='captcha' i]",
    "[id*='captcha' i]",
    "input[name*='captcha' i]",
    "input[id*='captcha' i]",
    "input[name*='challenge' i]",
    "input[id*='challenge' i]",
  ];

  async function pageSnapshot(extra = {}) {
    let details = {};
    try {
      details = await page.evaluate(() => {
        const safePath = (value) => {
          try {
            const parsed = new URL(value || location.href, location.href);
            return `${parsed.origin}${parsed.pathname}`;
          } catch (_) {
            return "unknown";
          }
        };
        const forms = Array.from(document.forms)
          .slice(0, 4)
          .map((form) => ({
            method: String(form.method || "get").toUpperCase(),
            action: safePath(form.action || location.href),
            fields: Array.from(form.elements)
              .filter((element) => element && element.tagName === "INPUT")
              .slice(0, 20)
              .map((input) => ({
                type: String(input.type || "text").toLowerCase(),
                name: String(input.name || "").slice(0, 80),
                id: String(input.id || "").slice(0, 80),
                autocomplete: String(input.autocomplete || "").slice(0, 80),
              })),
          }));
        return {
          page_url: safePath(location.href),
          page_title: String(document.title || "").slice(0, 120),
          forms,
        };
      });
    } catch (_) {
      details = { page_url: safeUrl(page.url()) };
    }

    return {
      stage,
      http_status: lastHttpStatus,
      response_url: safeUrl(lastResponseUrl),
      content_type: lastContentType,
      login_post_observed: loginPostObserved,
      list_price_post_observed: listPricePostObserved,
      list_price_request_body_length: listPriceRequestBodyLength,
      list_price_request_content_type: listPriceRequestContentType,
      ...details,
      ...extra,
    };
  }

  async function fail(code, message, extra = {}) {
    const error = new Error(message);
    error.code = code;
    error.diagnostics = await pageSnapshot(extra);
    throw error;
  }

  async function hasInteractiveChallenge() {
    return Boolean(await firstVisible(challengeSelectors));
  }

  async function isLoginState() {
    if (/\/login(?:\?|$)/i.test(page.url())) return true;
    const username = await firstVisible(usernameSelectors);
    const password = await firstVisible(passwordSelectors);
    return Boolean(username && password);
  }

  async function gotoPortal(url, nextStage) {
    stage = nextStage;
    let response;
    try {
      response = await page.goto(url, {
        waitUntil: "domcontentloaded",
        timeout: timeoutMs,
      });
    } catch (error) {
      await fail(
        "portal_unreachable",
        `Tankarta navigation failed during ${nextStage}: ${error.name || "Error"}`
      );
    }

    if (!response) {
      await fail("portal_unreachable", `Tankarta returned no response during ${nextStage}`);
    }

    lastHttpStatus = response.status();
    lastResponseUrl = response.url();
    lastContentType = response.headers()["content-type"] || "";

    if (lastHttpStatus >= 500) {
      await fail(
        "portal_unreachable",
        `Tankarta portal returned HTTP ${lastHttpStatus}`
      );
    }
    if (lastHttpStatus === 401 || lastHttpStatus === 403) {
      await fail(
        "portal_http_error",
        `Tankarta portal rejected navigation with HTTP ${lastHttpStatus}`
      );
    }

    return response;
  }

  async function clearBrowserState() {
    try {
      const client = await page.target().createCDPSession();
      await client.send("Network.clearBrowserCookies");
      await client.detach();
    } catch (_) {}

    await gotoPortal(LOGIN_URL, "login_page_navigation");
    try {
      await page.evaluate(() => {
        localStorage.clear();
        sessionStorage.clear();
      });
    } catch (_) {}
  }

  async function restoreSession() {
    stage = "session_restore";
    const saved = context.session || {};
    if (Array.isArray(saved.cookies) && saved.cookies.length) {
      try {
        await page.setCookie(...saved.cookies);
      } catch (_) {}
    }

    await gotoPortal(BASE_URL, "portal_navigation");

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

      try {
        const response = await page.reload({
          waitUntil: "domcontentloaded",
          timeout: timeoutMs,
        });
        if (response) {
          lastHttpStatus = response.status();
          lastResponseUrl = response.url();
          lastContentType = response.headers()["content-type"] || "";
        }
      } catch (error) {
        await fail(
          "portal_unreachable",
          `Tankarta session reload failed: ${error.name || "Error"}`
        );
      }
    }

    await delay(750);
    return !(await isLoginState());
  }

  async function loginFresh() {
    stage = "login_form";
    loginPostObserved = false;
    resetListPriceCapture();
    await clearBrowserState();

    const username = await waitForVisible(usernameSelectors, Math.min(timeoutMs, 15000));
    const password = await waitForVisible(passwordSelectors, Math.min(timeoutMs, 15000));
    if (!username || !password) {
      if (await hasInteractiveChallenge()) {
        await fail(
          "challenge_required",
          "Tankarta login requires an interactive verification challenge"
        );
      }
      await fail("login_form_changed", "Tankarta login fields were not found");
    }

    await typeInto(username, context.username);
    await typeInto(password, context.password);

    let submit = await firstVisible(["button[type='submit']", "input[type='submit']"]);
    if (!submit) {
      submit = await buttonByText(/p(?:r|ř)ihl[aá]sit|login|sign in|pokra[cč]ovat/i);
    }

    stage = "login_submit";
    const navigation = page
      .waitForNavigation({ waitUntil: "domcontentloaded", timeout: timeoutMs })
      .catch(() => null);

    if (submit) await submit.click();
    else await page.keyboard.press("Enter");

    await Promise.race([navigation, delay(Math.min(8000, timeoutMs))]);
    await delay(750);

    const otp = await firstVisible(otpSelectors);
    if (otp) {
      await fail(
        "two_factor_required",
        "Tankarta account requires two-factor authentication"
      );
    }

    if (await isLoginState()) {
      if (await hasInteractiveChallenge()) {
        await fail(
          "challenge_required",
          "Tankarta login requires an interactive verification challenge"
        );
      }
      await fail(
        "authentication_failed",
        "Tankarta login did not establish an authenticated session"
      );
    }
  }

  async function waitForNativeListPriceResponse(maximumMs) {
    const deadline = Date.now() + maximumMs;
    while (Date.now() < deadline) {
      if (listPriceCapturePromise) {
        try {
          return await listPriceCapturePromise;
        } catch (error) {
          await fail(
            "invalid_payload",
            `Tankarta list-price response could not be read: ${error.name || "Error"}`,
            { request_method: "POST" }
          );
        }
      }
      await delay(200);
    }
    return null;
  }

  async function triggerNativeListPriceRequest() {
    stage = "dashboard_list_price_wait";

    let response = await waitForNativeListPriceResponse(Math.min(timeoutMs, 10000));
    if (response) return response;

    if (await isLoginState()) {
      await fail("authentication_failed", "Tankarta session is not authenticated");
    }

    stage = "dashboard_reload";
    resetListPriceCapture();

    try {
      const navigation = await page.reload({
        waitUntil: "domcontentloaded",
        timeout: timeoutMs,
      });
      if (navigation) {
        lastHttpStatus = navigation.status();
        lastResponseUrl = navigation.url();
        lastContentType = navigation.headers()["content-type"] || "";
      }
    } catch (error) {
      await fail(
        "portal_unreachable",
        `Tankarta dashboard reload failed: ${error.name || "Error"}`
      );
    }

    response = await waitForNativeListPriceResponse(Math.min(timeoutMs, 15000));
    if (response) return response;

    if (await isLoginState()) {
      await fail("authentication_failed", "Tankarta session expired while loading dashboard");
    }

    await fail(
      "list_price_request_not_observed",
      "Tankarta dashboard did not send its list-price POST request",
      { request_method: "POST" }
    );
  }

  async function fetchPrices() {
    const response = await triggerNativeListPriceRequest();

    stage = "list_price_response";
    lastHttpStatus = response.status;
    lastResponseUrl = response.url;
    lastContentType = response.contentType;

    if (
      response.status === 401 ||
      response.status === 403 ||
      /\/login(?:\?|$)/i.test(response.url) ||
      (await isLoginState())
    ) {
      await fail("authentication_failed", "Tankarta session is not authenticated");
    }

    if (response.status === 404) {
      await fail(
        "endpoint_not_found",
        "Tankarta list-price POST endpoint returned HTTP 404",
        { request_method: "POST" }
      );
    }

    if (response.status < 200 || response.status >= 300) {
      await fail(
        "endpoint_http_error",
        `Tankarta list-price POST endpoint returned HTTP ${response.status}`,
        { request_method: "POST" }
      );
    }

    let decoded;
    try {
      decoded = JSON.parse(response.text);
    } catch (_) {
      if (/text\/html/i.test(response.contentType) && (await isLoginState())) {
        await fail("authentication_failed", "Tankarta returned the login page instead of JSON");
      }
      await fail(
        "invalid_payload",
        "Tankarta list-price POST response was not JSON",
        {
          request_method: "POST",
          response_length: String(response.text || "").length,
        }
      );
    }

    const array = Array.isArray(decoded)
      ? decoded
      : decoded && Array.isArray(decoded.data)
        ? decoded.data
        : null;
    if (!array) {
      await fail("invalid_payload", "Tankarta list-price JSON was not an array");
    }

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
    const sessionAuthenticated = await restoreSession();
    if (!sessionAuthenticated) {
      await loginFresh();
    }

    let prices;
    try {
      prices = await fetchPrices();
    } catch (error) {
      if (error.code !== "authentication_failed" || !sessionAuthenticated) {
        throw error;
      }
      await loginFresh();
      prices = await fetchPrices();
    }

    stage = "complete";
    return {
      data: {
        success: true,
        prices,
        session: await saveSession(),
        diagnostics: await pageSnapshot({ product_count: prices.length }),
      },
      type: "application/json",
    };
  } catch (error) {
    return {
      data: {
        success: false,
        code: error.code || "unknown",
        error: error.message || String(error),
        diagnostics: error.diagnostics || (await pageSnapshot()),
      },
      type: "application/json",
    };
  }
};
