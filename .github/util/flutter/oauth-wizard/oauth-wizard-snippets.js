/**
 * OAuth 마법사 산출물 생성 (분할 파일 — 함수 선언만, 상태·초기화는 oauth-wizard.js)
 *
 * 여기서 만드는 문자열(XML·yaml·Dart·명령어)은 복사해 쓰는 산출물이라 번역하지 않는다.
 * 두 언어에서 바이트 단위로 같아야 한다 (#769 규칙). 주석도 영문으로 둔다.
 *
 * 근거 문서
 *   Kakao : developers.kakao.com/docs/ko/flutter/getting-started, /ios/getting-started, /android/getting-started
 *   Google: pub.dev/packages/google_sign_in, google_sign_in_android, google_sign_in_ios
 */

/* eslint-disable no-unused-vars */

// 자리표시자·경로 상수는 oauth-wizard.js 에 둔다 (분할 파일은 함수 선언만)

// ============================================
// 값 검증·변환
// ============================================

/** Kakao 네이티브 앱 키: 32자리 16진 (REST API·JavaScript 키와 구분) */
function isValidKakaoNativeAppKey(value) {
    return /^[0-9a-fA-F]{32}$/.test(String(value || '').trim());
}

/** Google OAuth 클라이언트 ID: {번호}-{식별자}.apps.googleusercontent.com */
function isValidGoogleClientId(value) {
    return /^[0-9]+-[0-9a-z]+\.apps\.googleusercontent\.com$/.test(String(value || '').trim());
}

function isValidApplicationId(value) {
    return /^[a-zA-Z][a-zA-Z0-9_]*(\.[a-zA-Z][a-zA-Z0-9_]*)+$/.test(String(value || '').trim());
}

function isValidBundleId(value) {
    return /^[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+$/.test(String(value || '').trim());
}

/** SHA-1 입력 > 콜론 구분 대문자 (AA:BB:...) — 형식이 아니면 빈 문자열 */
function normalizeSha1(value) {
    const hex = String(value || '').replace(/[^0-9a-fA-F]/g, '').toUpperCase();
    if (hex.length !== 40) return '';
    return hex.match(/.{2}/g).join(':');
}

function isValidSha1(value) {
    return normalizeSha1(value) !== '';
}

/** SHA-1 > Kakao 키 해시 base64 (xxd -r -p | openssl base64 와 같음, oauth-wizard.py key-hash 와 같은 결과) */
function sha1ToKakaoKeyHash(value) {
    const normalized = normalizeSha1(value);
    if (!normalized) return '';
    const binary = normalized.split(':').map((pair) => String.fromCharCode(parseInt(pair, 16))).join('');
    return btoa(binary);
}

/** iOS 클라이언트 ID > REVERSED_CLIENT_ID (com.googleusercontent.apps.{번호}-{식별자}) */
function toReversedClientId(iosClientId) {
    const match = String(iosClientId || '').trim().match(/^([0-9]+-[0-9a-z]+)\.apps\.googleusercontent\.com$/);
    return match ? `com.googleusercontent.apps.${match[1]}` : 'com.googleusercontent.apps.YOUR_IOS_CLIENT_ID';
}

function kakaoKeyOrPlaceholder(value) {
    return isValidKakaoNativeAppKey(value) ? value.trim() : PLACEHOLDER_KAKAO_NATIVE_APP_KEY;
}

// ============================================
// 네이티브 설정 (AndroidManifest.xml · Info.plist)
// ============================================

/** AndroidManifest.xml <application> 안에 넣을 Kakao 로그인 액티비티 */
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

/** Info.plist: kakao{키} URL scheme + 카카오톡 앱 확인 허용 목록 */
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
// Dart 코드
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

/** iOS 빌드 job 에 넣을 스텝 — Secret 값으로 GoogleService-Info.plist 통째 생성 */
function buildIosGoogleServiceInfoStep() {
    return [
        '      # OAuth wizard: recreate GoogleService-Info.plist from the GitHub Secret (whole file)',
        '      - name: Create GoogleService-Info.plist',
        '        env:',
        '          GOOGLE_SERVICE_INFO_PLIST: ${{ secrets.GOOGLE_SERVICE_INFO_PLIST }}',
        '        run: |',
        '          if [ -z "$GOOGLE_SERVICE_INFO_PLIST" ]; then',
        '            echo "::error title=Missing secret::GOOGLE_SERVICE_INFO_PLIST is empty. Register it (OAuth wizard, Secrets step)."',
        '            exit 1',
        '          fi',
        '          mkdir -p ios/Runner',
        "          printf '%s\\n' \"$GOOGLE_SERVICE_INFO_PLIST\" > ios/Runner/GoogleService-Info.plist",
        '          echo "✅ ios/Runner/GoogleService-Info.plist created ($(wc -c < ios/Runner/GoogleService-Info.plist) bytes)"',
    ].join('\n');
}

/** 같은 결과를 cat << 'EOF' 로 쓰는 형태 (따옴표 EOF — 셸이 $ 를 풀지 않는다) */
function buildIosGoogleServiceInfoHeredocStep() {
    return [
        '      - name: Create GoogleService-Info.plist',
        '        run: |',
        '          mkdir -p ios/Runner',
        "          cat > ios/Runner/GoogleService-Info.plist << 'EOF'",
        '          ${{ secrets.GOOGLE_SERVICE_INFO_PLIST }}',
        '          EOF',
    ].join('\n');
}

/** 스텝을 넣을 자리 (앞뒤 기존 스텝 이름) */
function buildIosStepPlacementSnippet() {
    return [
        '      - name: Ensure .env file exists        # existing step',
        '        ...',
        '',
        '      # ⬇ paste the "Create GoogleService-Info.plist" step here',
        '',
        '      - name: Set up Flutter                 # existing step',
    ].join('\n');
}

/** Android 워크플로우 4종에 이미 있는 스텝 (참고용 — 추가하지 않는다) */
function buildAndroidGoogleServicesReferenceStep() {
    return [
        '      # Already in ANDROID-TEST-APK, ANDROID-PLAYSTORE-CICD, ANDROID-FIREBASE-CICD, ANDROID-SELFHOSTED-CICD',
        '      - name: Create Google-services.json',
        '        env:',
        '          GOOGLE_SERVICES_JSON: ${{ secrets.GOOGLE_SERVICES_JSON }}',
        '        run: |',
        "          printf '%s\\n' \"$GOOGLE_SERVICES_JSON\" > android/app/google-services.json",
    ].join('\n');
}

// ============================================
// .gitignore · 명령어
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

/** OS별 CLI 접두사 (macOS/Linux: python3 + /, Windows: python + \) */
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

/** setup 명령 — 선택한 제공자·옵션만 플래그로 */
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

/** 키 지문 확인 명령 (keytool) — 디버그·업로드 키 */
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
