/**
 * Kantata OX OAuth — Web App redirect + token exchange for Kantata Assist.
 *
 * Setup (Project Settings → Script properties):
 *   KANTATA_CLIENT_ID      — from Kantata OAuth app
 *   KANTATA_CLIENT_SECRET  — from Kantata OAuth app (treat as secret; restrict script edit access)
 *   KANTATA_REDIRECT_URI   — exact Web App URL (Deploy → copy URL ending in /exec)
 *
 * In Kantata, register the same KANTATA_REDIRECT_URI as the OAuth redirect URI.
 *
 * Deploy → New deployment → Type: Web app → Execute as: Me → Who has access: your org.
 * Users open the deployment URL, approve Kantata, then copy the JSON into:
 *   kantata import-credentials
 *
 * For production, add OAuth "state" validation (CacheService) on the callback.
 *
 * IMPORTANT: Web Apps are often shown inside a sandbox iframe (script.googleusercontent.com).
 * OAuth MUST navigate the top window, not the iframe — otherwise Kantata login fails
 * (browser shows "refused to connect" / net::ERR_BLOCKED, HAR status 0).
 */
var KANTATA_AUTHORIZE = 'https://app.mavenlink.com/oauth/authorize';
var KANTATA_TOKEN = 'https://app.mavenlink.com/oauth/token';

function doGet(e) {
  var props = PropertiesService.getScriptProperties();
  var clientId = props.getProperty('KANTATA_CLIENT_ID');
  var clientSecret = props.getProperty('KANTATA_CLIENT_SECRET');
  var redirectUri = props.getProperty('KANTATA_REDIRECT_URI');
  if (!clientId || !clientSecret || !redirectUri) {
    return HtmlService.createHtmlOutput(
      '<p>Missing Script properties. Set KANTATA_CLIENT_ID, KANTATA_CLIENT_SECRET, KANTATA_REDIRECT_URI.</p>'
    );
  }

  if (e.parameter.error) {
    var desc = e.parameter.error_description || e.parameter.error;
    return HtmlService.createHtmlOutput('<p>OAuth error: ' + escapeHtml_(String(desc)) + '</p>');
  }

  if (!e.parameter.code) {
    var authUrl =
      KANTATA_AUTHORIZE +
      '?response_type=code' +
      '&client_id=' + encodeURIComponent(clientId) +
      '&redirect_uri=' + encodeURIComponent(redirectUri);
    // Break out of the Apps Script iframe: navigate the full tab to Kantata.
    return HtmlService.createHtmlOutput(
      '<!DOCTYPE html><html><head><base target="_top"></head><body>' +
        '<p>Redirecting to Kantata…</p>' +
        '<script>(function(){var u=' +
        JSON.stringify(authUrl) +
        ';try{window.top.location.replace(u);}catch(e){window.top.location.href=u;}})();</script>' +
        '<p>If nothing happens, <a href="' +
        escapeHtml_(authUrl) +
        '" target="_top">continue to Kantata in this tab</a>.</p></body></html>'
    );
  }

  var code = e.parameter.code;
  var tokenPayload = {
    grant_type: 'authorization_code',
    client_id: clientId,
    client_secret: clientSecret,
    code: code,
    redirect_uri: redirectUri,
  };

  var resp = UrlFetchApp.fetch(KANTATA_TOKEN, {
    method: 'post',
    payload: tokenPayload,
    muteHttpExceptions: true,
  });

  var status = resp.getResponseCode();
  var bodyText = resp.getContentText();
  if (status < 200 || status >= 300) {
    return HtmlService.createHtmlOutput(
      '<p>Token exchange failed (' +
        status +
        ').</p><pre style="white-space:pre-wrap;word-break:break-all">' +
        escapeHtml_(bodyText) +
        '</pre>'
    );
  }

  var body;
  try {
    body = JSON.parse(bodyText);
  } catch (err) {
    return HtmlService.createHtmlOutput('<p>Invalid JSON from token endpoint.</p>');
  }

  if (!body.access_token) {
    return HtmlService.createHtmlOutput(
      '<p>Unexpected token response.</p><pre>' + escapeHtml_(bodyText) + '</pre>'
    );
  }

  var out = { access_token: body.access_token, token_type: body.token_type || 'bearer' };
  if (body.refresh_token) {
    out.refresh_token = body.refresh_token;
  }
  var jsonStr = JSON.stringify(out, null, 2);

  return HtmlService.createHtmlOutput(
    '<p>Copy the JSON below, then run locally:</p>' +
      '<pre style="background:#f5f5f5;padding:12px;word-break:break-all">' +
      escapeHtml_(jsonStr) +
      '</pre>' +
      '<p><code>pbpaste | kantata import-credentials</code> (macOS) or ' +
      '<code>pbpaste | uvx --from git+https://github.com/kleinjoshuaa/kantata-mcp.git kantata import-credentials</code>, ' +
      'or save to a file and use <code>--file</code>.</p>'
  );
}

function escapeHtml_(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
