/**
 * OAuth wizard output generation (split file — function declarations only; state and init in oauth-wizard.js)
 *
 * Strings built here (XML, yaml, Dart, commands) are outputs users copy, so they are not translated.
 * They must be byte-identical in both languages (#769 rule). Comments are kept in English too.
 *
 * Reference docs
 *   Kakao : developers.kakao.com/docs/ko/flutter/getting-started, /ios/getting-started, /android/getting-started
 *   Google: pub.dev/packages/google_sign_in, google_sign_in_android, google_sign_in_ios
 */

/* eslint-disable no-unused-vars */

// Placeholder and path constants live in oauth-wizard.js (split files hold only function declarations)

// ============================================
// Value validation/conversion
// ============================================

/** Kakao native app key: 32 hex characters (distinct from the REST API and JavaScript keys) */
function isValidKakaoNativeAppKey(value) {
    return /^[0-9a-fA-F]{32}$/.test(String(value || '').trim());
}

/** Google OAuth client ID: {number}-{identifier}.apps.googleusercontent.com */
function isValidGoogleClientId(value) {
    return /^[0-9]+-[0-9a-z]+\.apps\.googleusercontent\.com$/.test(String(value || '').trim());
}

function isValidApplicationId(value) {
    return /^[a-zA-Z][a-zA-Z0-9_]*(\.[a-zA-Z][a-zA-Z0-9_]*)+$/.test(String(value || '').trim());
}

function isValidBundleId(value) {
    return /^[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+$/.test(String(value || '').trim());
}

/** SHA-1 input > colon-separated uppercase (AA:BB:...) — empty string if not the format */
function normalizeSha1(value) {
    const hex = String(value || '').replace(/[^0-9a-fA-F]/g, '').toUpperCase();
    if (hex.length !== 40) return '';
    return hex.match(/.{2}/g).join(':');
}

function isValidSha1(value) {
    return normalizeSha1(value) !== '';
}

/** SHA-1 > Kakao key hash base64 (same as xxd -r -p | openssl base64, same result as oauth-wizard.py key-hash) */
function sha1ToKakaoKeyHash(value) {
    const normalized = normalizeSha1(value);
    if (!normalized) return '';
    const binary = normalized.split(':').map((pair) => String.fromCharCode(parseInt(pair, 16))).join('');
    return btoa(binary);
}

/** iOS client ID > REVERSED_CLIENT_ID (com.googleusercontent.apps.{number}-{identifier}) */
function toReversedClientId(iosClientId) {
    const match = String(iosClientId || '').trim().match(/^([0-9]+-[0-9a-z]+)\.apps\.googleusercontent\.com$/);
    return match ? `com.googleusercontent.apps.${match[1]}` : 'com.googleusercontent.apps.YOUR_IOS_CLIENT_ID';
}

function kakaoKeyOrPlaceholder(value) {
    return isValidKakaoNativeAppKey(value) ? value.trim() : PLACEHOLDER_KAKAO_NATIVE_APP_KEY;
}

// ============================================
// Native config (AndroidManifest.xml, Info.plist)
// ============================================

/** Kakao login activity to put inside <application> in AndroidManifest.xml */
function buildKakaoManifestSnippet(nativeAppKey) {
    const key = kakaoKeyOrPlaceholder(nativeAppKey);
    return [
        '<!-- android/app/src/main/AndroidManifest.xml, inside <application> -->',
        '<activity',
        '    android:name="com.kakao.sdk.flutter.auth.AuthCodeHandlerActivity"',
        '    android:exported="true">',
        '    <intent-filter android:label="flutter_web_auth">',
        '        <action android:name="android.intent.action.VIEW" />',
        '        <category android:name="android.intent.category.DEFAULT" />',
        '        <category android:name="android.intent.category.BROWSABLE" />',
        `        <data android:scheme="kakao${key}" android:host="oauth" />`,
        '    </intent-filter>',
        '</activity>',
    ].join('\n');
}

/** Info.plist: kakao{key} URL scheme + KakaoTalk app query allow list */
function buildKakaoPlistSnippet(nativeAppKey) {
    const key = kakaoKeyOrPlaceholder(nativeAppKey);
    return [
        '<!-- ios/Runner/Info.plist, inside the top-level <dict> -->',
        '<!-- If CFBundleURLTypes already exists, add only the inner <dict> to its <array>. -->',
        '<key>CFBundleURLTypes</key>',
        '<array>',
        '    <dict>',
        '        <key>CFBundleTypeRole</key>',
        '        <string>Editor</string>',
        '        <key>CFBundleURLSchemes</key>',
        '        <array>',
        `            <string>kakao${key}</string>`,
        '        </array>',
        '    </dict>',
        '</array>',
        '<key>LSApplicationQueriesSchemes</key>',
        '<array>',
        '    <string>kakaokompassauth</string>',
        '    <string>kakaolink</string>',
        '</array>',
    ].join('\n');
}

/** Info.plist: GIDClientID·GIDServerClientID + REVERSED_CLIENT_ID URL scheme */
function buildGooglePlistSnippet(iosClientId, serverClientId) {
    const clientId = isValidGoogleClientId(iosClientId) ? iosClientId.trim() : PLACEHOLDER_GOOGLE_IOS_CLIENT_ID;
    const lines = [
        '<!-- ios/Runner/Info.plist, inside the top-level <dict> -->',
        '<!-- If CFBundleURLTypes already exists, add only the inner <dict> to its <array>. -->',
        '<key>GIDClientID</key>',
        `<string>${clientId}</string>`,
    ];
    if (isValidGoogleClientId(serverClientId)) {
        lines.push('<key>GIDServerClientID</key>', `<string>${serverClientId.trim()}</string>`);
    }
    lines.push(
        '<key>CFBundleURLTypes</key>',
        '<array>',
        '    <dict>',
        '        <key>CFBundleTypeRole</key>',
        '        <string>Editor</string>',
        '        <key>CFBundleURLSchemes</key>',
        '        <array>',
        `            <string>${toReversedClientId(iosClientId)}</string>`,
        '        </array>',
        '    </dict>',
        '</array>',
    );
    return lines.join('\n');
}

// ============================================
// Dart code
// ============================================

function buildKakaoDartSnippet(nativeAppKey) {
    const key = kakaoKeyOrPlaceholder(nativeAppKey);
    return [
        '// pubspec: flutter pub add kakao_flutter_sdk_user',
        "import 'package:flutter/material.dart';",
        "import 'package:flutter/services.dart';",
        "import 'package:kakao_flutter_sdk_user/kakao_flutter_sdk_user.dart';",
        '',
        'Future<void> main() async {',
        '  WidgetsFlutterBinding.ensureInitialized();',
        '  // The Native App Key is a public app identifier (it is also in AndroidManifest.xml / Info.plist).',
        `  await KakaoSdk.init(nativeAppKey: '${key}');`,
        '  runApp(const MyApp());',
        '}',
        '',
        '/// KakaoTalk app first, Kakao Account (browser) as fallback. Returns null if the user cancels.',
        'Future<OAuthToken?> signInWithKakao() async {',
        '  if (await isKakaoTalkInstalled()) {',
        '    try {',
        '      return await UserApi.instance.loginWithKakaoTalk();',
        '    } catch (error) {',
        "      if (error is PlatformException && error.code == 'CANCELED') return null;",
        '      return await UserApi.instance.loginWithKakaoAccount();',
        '    }',
        '  }',
        '  return await UserApi.instance.loginWithKakaoAccount();',
        '}',
    ].join('\n');
}

function buildGoogleDartSnippet(serverClientId) {
    const serverId = isValidGoogleClientId(serverClientId) ? serverClientId.trim() : PLACEHOLDER_GOOGLE_SERVER_CLIENT_ID;
    return [
        '// pubspec: flutter pub add google_sign_in',
        "import 'package:google_sign_in/google_sign_in.dart';",
        '',
        '// Web application client ID. Android needs it unless google-services.json has a web client entry.',
        `const googleServerClientId = '${serverId}';`,
        '',
        '/// Call once at startup (e.g. in main() before runApp).',
        'Future<void> initGoogleSignIn() async {',
        '  // iOS reads GIDClientID from Info.plist, so clientId is not passed here.',
        '  await GoogleSignIn.instance.initialize(serverClientId: googleServerClientId);',
        '}',
        '',
        'Future<GoogleSignInAccount?> signInWithGoogle() async {',
        '  if (!GoogleSignIn.instance.supportsAuthenticate()) return null;',
        '  return GoogleSignIn.instance.authenticate();',
        '}',
    ].join('\n');
}

// ============================================
// CI/CD (GitHub Actions)
// ============================================

/** Restore step the template already runs (#785 firebase_config_files.py) — for reference, not added again */
function buildBuiltInRestoreStepsReference() {
    return [
        '      # Android workflows and Flutter CI',
        '      - name: Create Google-services.json',
        '        env:',
        '          GOOGLE_SERVICES_JSON: ${{ secrets.GOOGLE_SERVICES_JSON }}',
        '        run: python3 "$GITHUB_WORKSPACE/.github/scripts/firebase_config_files.py" restore --platform android --app-root .',
        '',
        '      # iOS TestFlight workflows (after "Ensure .env file exists") and Flutter CI',
        '      - name: Create GoogleService-Info.plist',
        '        env:',
        '          GOOGLE_SERVICE_INFO_PLIST: ${{ secrets.GOOGLE_SERVICE_INFO_PLIST }}',
        '        run: python3 "$GITHUB_WORKSPACE/.github/scripts/firebase_config_files.py" restore --platform ios --app-root .',
    ].join('\n');
}

/** Check the script exists > otherwise update the template (per OS) */
function buildTemplateCheckCommand(operatingSystem) {
    const check = operatingSystem === 'windows'
        ? 'Test-Path .github\\scripts\\firebase_config_files.py'
        : 'ls .github/scripts/firebase_config_files.py';
    return [
        `${check}    # found: the templates restore both files`,
        'npx projectops    # not found: update the templates',
    ].join('\n');
}

/** Manual step for old templates — skips when the Secret is empty, like the script (raw plist only) */
function buildFallbackIosRestoreStep() {
    return [
        '      # Fallback for templates without .github/scripts/firebase_config_files.py.',
        '      # Prefer updating with npx projectops; remove this step after updating.',
        '      - name: Create GoogleService-Info.plist',
        '        env:',
        '          GOOGLE_SERVICE_INFO_PLIST: ${{ secrets.GOOGLE_SERVICE_INFO_PLIST }}',
        '        run: |',
        '          if [ -z "$GOOGLE_SERVICE_INFO_PLIST" ]; then',
        '            echo "GOOGLE_SERVICE_INFO_PLIST not set, skipping"',
        '            exit 0',
        '          fi',
        '          mkdir -p ios/Runner',
        "          printf '%s\\n' \"$GOOGLE_SERVICE_INFO_PLIST\" > ios/Runner/GoogleService-Info.plist",
        '          echo "ios/Runner/GoogleService-Info.plist created"',
    ].join('\n');
}

// ============================================
// .gitignore / commands
// ============================================

function buildGitignoreSnippet(includeFirebaseFiles) {
    const lines = [
        '# OAuth wizard (projectops)',
        `${OAUTH_EXPORT_FILE_PREFIX_SECRETS}*.json`,
        `${OAUTH_EXPORT_FILE_PREFIX_SECRETS}*.txt`,
        `${OAUTH_EXPORT_FILE_PREFIX_SETUP}*.zip`,
    ];
    if (includeFirebaseFiles) {
        lines.push('android/app/google-services.json', 'ios/Runner/GoogleService-Info.plist');
    }
    return lines.join('\n');
}

function buildUntrackCommand() {
    return 'git rm --cached --ignore-unmatch android/app/google-services.json ios/Runner/GoogleService-Info.plist';
}

/** CLI prefix per OS (macOS/Linux: python3 + /, Windows: python + \) */
function buildCliPrefix(operatingSystem) {
    return operatingSystem === 'windows'
        ? `python ${OAUTH_WIZARD_CLI_PATH.replace(/\//g, '\\')}`
        : `python3 ${OAUTH_WIZARD_CLI_PATH}`;
}

function quoteProjectPath(projectPath, operatingSystem) {
    const raw = String(projectPath || '.').trim() || '.';
    const path = operatingSystem === 'windows' ? raw.replace(/\//g, '\\') : raw;
    return /\s/.test(path) ? `"${path}"` : path;
}

function buildDetectCommand(operatingSystem, projectPath) {
    return `${buildCliPrefix(operatingSystem)} detect --project-path ${quoteProjectPath(projectPath, operatingSystem)}`;
}

/** setup command — only the chosen providers/options as flags */
function buildSetupCommand(operatingSystem, options) {
    const parts = [`${buildCliPrefix(operatingSystem)} setup`, `--project-path ${quoteProjectPath(options.projectPath, operatingSystem)}`];
    if (options.useKakao) parts.push(`--kakao-native-app-key ${kakaoKeyOrPlaceholder(options.kakaoNativeAppKey)}`);
    if (options.useGoogle) {
        parts.push(`--google-ios-client-id ${isValidGoogleClientId(options.googleIosClientId) ? options.googleIosClientId.trim() : PLACEHOLDER_GOOGLE_IOS_CLIENT_ID}`);
        if (isValidGoogleClientId(options.googleServerClientId)) {
            parts.push(`--google-server-client-id ${options.googleServerClientId.trim()}`);
        }
    }
    if (options.updateGitignore) {
        parts.push('--update-gitignore');
        if (options.includeFirebaseFiles) parts.push('--firebase-files');
    }
    if (options.isDryRun) parts.push('--dry-run');
    return parts.join(' ');
}

/** Key fingerprint command (keytool) — debug and upload keys */
function buildKeytoolCommands(operatingSystem) {
    const debugKeystore = operatingSystem === 'windows'
        ? '"$env:USERPROFILE\\.android\\debug.keystore"'
        : '~/.android/debug.keystore';
    return {
        debug: `keytool -list -v -keystore ${debugKeystore} -alias androiddebugkey -storepass android -keypass android`,
        upload: 'keytool -list -v -keystore android/app/keystore/key.jks -alias YOUR_KEY_ALIAS',
        cliDebug: `${buildCliPrefix(operatingSystem)} fingerprints`,
        cliUpload: `${buildCliPrefix(operatingSystem)} fingerprints --keystore android/app/keystore/key.jks --alias YOUR_KEY_ALIAS --storepass YOUR_STORE_PASSWORD`,
        kakaoOpenssl: 'keytool -exportcert -alias androiddebugkey -keystore ~/.android/debug.keystore -storepass android -keypass android | openssl sha1 -binary | openssl base64',
    };
}
