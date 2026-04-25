/**
 * Kantata OAuth broker sample for Google Apps Script Web App.
 *
 * Endpoints (GET):
 *   ?action=start
 *   ?action=callback&code=...&state=...
 *   ?action=poll&session_id=...&poll_token=...
 *
 * Script Properties required:
 *   KANTATA_CLIENT_ID
 *   KANTATA_CLIENT_SECRET
 *   KANTATA_AUTHORIZE_URL (optional; default https://app.mavenlink.com/oauth/authorize)
 *   KANTATA_TOKEN_URL (optional; default https://app.mavenlink.com/oauth/token)
 *   BROKER_SESSION_TTL_SECONDS (optional; default 600)
 *
 * NOTE:
 * - This sample keeps session state in Script Properties for simplicity.
 * - For higher scale/sensitivity, store sessions in a stronger backing store.
 * - Do not log raw tokens. Keep access to this Apps Script project tightly restricted.
 */

function doGet(e) {
  var action = (e && e.parameter && e.parameter.action) || '';
  if (action === 'start') return handleStart_();
  if (action === 'callback') return handleCallback_(e);
  if (action === 'poll') return handlePoll_(e);
  return json_({ error: 'unknown_action', message: 'Use action=start|callback|poll' }, 400);
}

function handleStart_() {
  var cfg = getConfig_();
  var now = Date.now();
  var sessionId = randomId_();
  var pollToken = randomId_();
  var state = randomId_();
  var expiresAtMs = now + cfg.ttlSeconds * 1000;
  var baseUrl = ScriptApp.getService().getUrl();
  var callbackUrl = addQueryParam_(baseUrl, 'action', 'callback');

  var authUrl =
    cfg.authorizeUrl +
    '?' +
    toQuery_({
      response_type: 'code',
      client_id: cfg.clientId,
      redirect_uri: callbackUrl,
      state: state,
    });

  var session = {
    status: 'pending',
    state: state,
    poll_token: pollToken,
    expires_at_ms: expiresAtMs,
    created_at_ms: now,
    callback_url: callbackUrl,
  };
  putSession_(sessionId, session);
  putSessionStateIndex_(state, sessionId);

  return json_({
    session_id: sessionId,
    authorize_url: authUrl,
    poll_url: addQueryParam_(baseUrl, 'action', 'poll'),
    poll_token: pollToken,
    expires_in_seconds: cfg.ttlSeconds,
  });
}

function handleCallback_(e) {
  var state = getParam_(e, 'state');
  var code = getParam_(e, 'code');
  var oauthError = getParam_(e, 'error');
  var oauthErrorDescription = getParam_(e, 'error_description');
  var sessionId = getSessionIdByState_(state);
  var sess = getSession_(sessionId);
  if (!sess) return html_('Invalid or expired session.');
  if (isExpired_(sess)) {
    sess.status = 'expired';
    putSession_(sessionId, sess);
    return html_('Session expired. Start login again.');
  }
  if (!state || state !== sess.state) {
    sess.status = 'error';
    sess.error = 'invalid_state';
    putSession_(sessionId, sess);
    return html_('State mismatch. Please restart login.');
  }
  if (oauthError) {
    sess.status = 'error';
    sess.error = oauthErrorDescription || oauthError;
    putSession_(sessionId, sess);
    return html_('OAuth denied/cancelled. Return to your terminal.');
  }
  if (!code) {
    sess.status = 'error';
    sess.error = 'missing_code';
    putSession_(sessionId, sess);
    return html_('Missing code. Please retry.');
  }

  var cfg = getConfig_();
  var tokenResp;
  try {
    tokenResp = UrlFetchApp.fetch(cfg.tokenUrl, {
      method: 'post',
      payload: {
        grant_type: 'authorization_code',
        client_id: cfg.clientId,
        client_secret: cfg.clientSecret,
        code: code,
        redirect_uri: addQueryParam_(ScriptApp.getService().getUrl(), 'action', 'callback'),
      },
      muteHttpExceptions: true,
      headers: { Accept: 'application/json' },
    });
  } catch (err) {
    sess.status = 'error';
    sess.error = 'token_exchange_failed';
    putSession_(sessionId, sess);
    return html_('Token exchange failed. Please retry.');
  }

  var codeNum = tokenResp.getResponseCode();
  var bodyText = tokenResp.getContentText();
  if (codeNum < 200 || codeNum >= 300) {
    sess.status = 'error';
    sess.error = 'token_exchange_http_' + codeNum;
    putSession_(sessionId, sess);
    return html_('Token exchange failed. Return to terminal for details.');
  }

  var tokenJson;
  try {
    tokenJson = JSON.parse(bodyText);
  } catch (_parseErr) {
    sess.status = 'error';
    sess.error = 'token_response_parse_failed';
    putSession_(sessionId, sess);
    return html_('Token parse failed. Please retry.');
  }
  if (!tokenJson || !tokenJson.access_token) {
    sess.status = 'error';
    sess.error = 'missing_access_token';
    putSession_(sessionId, sess);
    return html_('No access token received. Please retry.');
  }

  sess.status = 'complete';
  sess.access_token = tokenJson.access_token;
  sess.token_type = tokenJson.token_type || 'bearer';
  putSession_(sessionId, sess);
  return html_('Kantata login complete. You can close this tab and return to your terminal.');
}

function handlePoll_(e) {
  var sessionId = getParam_(e, 'session_id');
  var pollToken = getParam_(e, 'poll_token');
  var sess = getSession_(sessionId);
  if (!sess) return json_({ status: 'expired', error: 'unknown_session' }, 404);
  if (isExpired_(sess)) {
    deleteSession_(sessionId);
    return json_({ status: 'expired', error: 'expired' }, 410);
  }
  if (!pollToken || pollToken !== sess.poll_token) {
    return json_({ status: 'error', error: 'invalid_poll_token' }, 403);
  }
  if (sess.status === 'pending') return json_({ status: 'pending' });
  if (sess.status === 'error') {
    deleteSession_(sessionId);
    return json_({ status: 'error', error: sess.error || 'oauth_error' });
  }
  if (sess.status === 'complete') {
    var token = sess.access_token;
    var tokenType = sess.token_type || 'bearer';
    deleteSession_(sessionId); // one-time retrieval
    return json_({ status: 'complete', access_token: token, token_type: tokenType });
  }
  return json_({ status: 'error', error: 'unknown_status' }, 500);
}

function getConfig_() {
  var props = PropertiesService.getScriptProperties();
  var clientId = props.getProperty('KANTATA_CLIENT_ID');
  var clientSecret = props.getProperty('KANTATA_CLIENT_SECRET');
  if (!clientId || !clientSecret) {
    throw new Error('Missing KANTATA_CLIENT_ID or KANTATA_CLIENT_SECRET in Script Properties');
  }
  return {
    clientId: clientId,
    clientSecret: clientSecret,
    authorizeUrl: props.getProperty('KANTATA_AUTHORIZE_URL') || 'https://app.mavenlink.com/oauth/authorize',
    tokenUrl: props.getProperty('KANTATA_TOKEN_URL') || 'https://app.mavenlink.com/oauth/token',
    ttlSeconds: Number(props.getProperty('BROKER_SESSION_TTL_SECONDS') || '600'),
  };
}

function sessionKey_(sessionId) {
  return 'oauth_session:' + sessionId;
}

function putSession_(sessionId, obj) {
  PropertiesService.getScriptProperties().setProperty(sessionKey_(sessionId), JSON.stringify(obj));
}

function stateKey_(state) {
  return 'oauth_state:' + state;
}

function putSessionStateIndex_(state, sessionId) {
  if (!state || !sessionId) return;
  PropertiesService.getScriptProperties().setProperty(stateKey_(state), sessionId);
}

function getSessionIdByState_(state) {
  if (!state) return '';
  return PropertiesService.getScriptProperties().getProperty(stateKey_(state)) || '';
}

function getSession_(sessionId) {
  if (!sessionId) return null;
  var raw = PropertiesService.getScriptProperties().getProperty(sessionKey_(sessionId));
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch (_err) {
    return null;
  }
}

function deleteSession_(sessionId) {
  var sess = getSession_(sessionId);
  if (sess && sess.state) {
    PropertiesService.getScriptProperties().deleteProperty(stateKey_(sess.state));
  }
  PropertiesService.getScriptProperties().deleteProperty(sessionKey_(sessionId));
}

function isExpired_(sess) {
  return !sess || !sess.expires_at_ms || Date.now() > Number(sess.expires_at_ms);
}

function randomId_() {
  return Utilities.getUuid().replace(/-/g, '') + '_' + String(Date.now());
}

function getParam_(e, name) {
  return (e && e.parameter && e.parameter[name]) || '';
}

function toQuery_(obj) {
  var parts = [];
  Object.keys(obj).forEach(function (k) {
    parts.push(encodeURIComponent(k) + '=' + encodeURIComponent(String(obj[k])));
  });
  return parts.join('&');
}

function addQueryParam_(url, key, value) {
  var sep = url.indexOf('?') >= 0 ? '&' : '?';
  return url + sep + encodeURIComponent(key) + '=' + encodeURIComponent(String(value));
}

function json_(payload, statusCode) {
  var out = ContentService.createTextOutput(JSON.stringify(payload));
  out.setMimeType(ContentService.MimeType.JSON);
  return out;
}

function html_(message) {
  var html = HtmlService.createHtmlOutput(
    '<!doctype html><html><body><p>' + escapeHtml_(message) + '</p></body></html>'
  );
  return html;
}

function escapeHtml_(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}
