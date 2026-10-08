/**
 * Project Hydra - Web Crypto JWT Helper (Zero external dependencies)
 * Algorithm: HS256 using native crypto.subtle
 */

function base64urlEncode(bufferOrString) {
  let base64 = '';
  if (typeof bufferOrString === 'string') {
    const bytes = new TextEncoder().encode(bufferOrString);
    let binary = '';
    for (let i = 0; i < bytes.byteLength; i++) {
      binary += String.fromCharCode(bytes[i]);
    }
    base64 = btoa(binary);
  } else {
    let binary = '';
    const bytes = new Uint8Array(bufferOrString);
    for (let i = 0; i < bytes.byteLength; i++) {
      binary += String.fromCharCode(bytes[i]);
    }
    base64 = btoa(binary);
  }
  return base64.replace(/=/g, '').replace(/\+/g, '-').replace(/\//g, '_');
}

function base64urlDecode(str) {
  let base64 = str.replace(/-/g, '+').replace(/_/g, '/');
  while (base64.length % 4) {
    base64 += '=';
  }
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes;
}

async function getHmacKey(secret) {
  const enc = new TextEncoder();
  return await crypto.subtle.importKey(
    'raw',
    enc.encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign', 'verify']
  );
}

/**
 * Sign a JWT token
 * @param {Object} payload Payload object
 * @param {string} secret HMAC Secret
 * @returns {Promise<string>} Signed JWT token
 */
export async function signJwt(payload, secret) {
  const header = { alg: 'HS256', typ: 'JWT' };
  const encodedHeader = base64urlEncode(JSON.stringify(header));
  const encodedPayload = base64urlEncode(JSON.stringify(payload));
  const dataToSign = `${encodedHeader}.${encodedPayload}`;

  const key = await getHmacKey(secret);
  const signature = await crypto.subtle.sign(
    'HMAC',
    key,
    new TextEncoder().encode(dataToSign)
  );

  const encodedSignature = base64urlEncode(signature);
  return `${dataToSign}.${encodedSignature}`;
}

/**
 * Verify a JWT token
 * @param {string} token JWT token string
 * @param {string} secret HMAC secret
 * @param {string|null} expectedIp Client IP to match against payload.ip if IP binding is enabled
 * @returns {Promise<{ valid: boolean, payload?: Object, error?: string }>}
 */
export async function verifyJwt(token, secret, expectedIp = null) {
  if (!token || typeof token !== 'string') {
    return { valid: false, error: 'Token missing or invalid format' };
  }

  const parts = token.split('.');
  if (parts.length !== 3) {
    return { valid: false, error: 'Malformed JWT structure' };
  }

  const [encodedHeader, encodedPayload, encodedSignature] = parts;
  const dataToVerify = `${encodedHeader}.${encodedPayload}`;

  try {
    const key = await getHmacKey(secret);
    const signatureBytes = base64urlDecode(encodedSignature);
    const isValidSignature = await crypto.subtle.verify(
      'HMAC',
      key,
      signatureBytes,
      new TextEncoder().encode(dataToVerify)
    );

    if (!isValidSignature) {
      return { valid: false, error: 'Invalid HMAC signature' };
    }

    const payloadJson = new TextDecoder().decode(base64urlDecode(encodedPayload));
    const payload = JSON.parse(payloadJson);

    // 1. Check expiration
    const now = Math.floor(Date.now() / 1000);
    if (payload.exp && payload.exp < now) {
      return { valid: false, error: 'Link expired' };
    }

    // 2. Anti-Leech Check: IP Binding verification
    if (expectedIp && payload.ip && payload.ip !== expectedIp) {
      return { 
        valid: false, 
        error: `Anti-leech violation: Request IP (${expectedIp}) does not match authorized IP (${payload.ip})` 
      };
    }

    return { valid: true, payload };
  } catch (err) {
    return { valid: false, error: err.message };
  }
}
