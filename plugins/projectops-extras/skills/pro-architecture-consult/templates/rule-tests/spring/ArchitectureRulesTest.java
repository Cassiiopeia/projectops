package architecture;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;
import java.util.regex.Pattern;
import java.util.stream.Collectors;
import java.util.stream.Stream;
import org.junit.jupiter.api.DynamicTest;
import org.junit.jupiter.api.TestFactory;

/**
 * 아키텍처 규칙 테스트: docs/architecture/rules/<id>.rule 위반 <-> <id>.allow 대조
 * 규칙은 rules 폴더에서 고친다 (이 파일은 pro-architecture-consult 템플릿 — 판정 로직만)
 */
class ArchitectureRulesTest {

  // 탐색 제외 폴더 (다른 스택 템플릿과 같은 목록)
  static final Set<String> SKIPPED_DIRECTORY_NAMES = Set.of(
      ".git", "build", "dist", "node_modules", ".dart_tool", "Pods", ".gradle",
      "venv", ".venv", "__pycache__", ".next", "out", "target", ".idea");
  static final Set<String> LIST_KEYS = Set.of("paths", "extensions", "exclude");
  // 규칙 파일 자신은 판정 대상에서 늘 제외
  static final String ALWAYS_EXCLUDED_PREFIX = "docs/architecture/";

  @TestFactory
  Stream<DynamicTest> architectureRules() throws IOException {
    Path rulesDirectory = findRulesDirectory(Path.of("").toAbsolutePath());
    if (rulesDirectory == null) {
      return Stream.empty();
    }
    Path repositoryRoot = rulesDirectory.getParent().getParent().getParent();
    try (Stream<Path> files = Files.list(rulesDirectory)) {
      List<Path> ruleFiles = files.filter(p -> p.toString().endsWith(".rule")).sorted().collect(Collectors.toList());
      return ruleFiles.stream().map(ruleFile -> DynamicTest.dynamicTest(
          "architecture rule: " + ruleFile.getFileName(), () -> assertRule(repositoryRoot, rulesDirectory, ruleFile)));
    }
  }

  /** 새 위반 없음 + 고쳐진 항목이 동결 목록에 남지 않음 */
  static void assertRule(Path repositoryRoot, Path rulesDirectory, Path ruleFile) {
    Map<String, Object> rule = parseRule(ruleFile);
    String ruleId = (String) rule.get("id");
    assertFalse(((String) rule.get("pattern")).isEmpty(), ruleId + ".rule: pattern 키가 없다");
    Set<String> violating = new TreeSet<>(findViolatingFiles(repositoryRoot, rule));
    Set<String> allowed = new TreeSet<>(readAllowEntries(rulesDirectory.resolve(ruleId + ".allow")));

    // 새 위반 (동결 목록에 없는 파일) > 코드를 고친다
    Set<String> newViolations = new TreeSet<>(violating);
    newViolations.removeAll(allowed);
    assertEquals(Collections.emptySet(), newViolations, "[" + ruleId + "] 새 위반: " + newViolations);
    // 고쳐진 항목 > 동결 목록에서 지운다 (목록이 느슨해지지 않게)
    Set<String> fixedEntries = new TreeSet<>(allowed);
    fixedEntries.removeAll(violating);
    assertEquals(Collections.emptySet(), fixedEntries,
        "[" + ruleId + "] 고쳐졌으니 " + ruleId + ".allow 에서 지운다: " + fixedEntries);
  }

  /** 현재 폴더부터 위로 docs/architecture/rules 탐색 (Gradle 은 모듈 폴더에서 테스트를 돌린다) */
  static Path findRulesDirectory(Path start) {
    for (Path directory = start; directory != null; directory = directory.getParent()) {
      Path candidate = directory.resolve("docs").resolve("architecture").resolve("rules");
      if (Files.isDirectory(candidate)) {
        return candidate;
      }
    }
    return null;
  }

  /** key=value (첫 = 에서만 자름, # 주석) > 규칙 — Properties 는 정규식 백슬래시를 먹어서 직접 파싱 */
  static Map<String, Object> parseRule(Path ruleFile) {
    String fileName = ruleFile.getFileName().toString();
    Map<String, Object> rule = new HashMap<>();
    rule.put("id", fileName.substring(0, fileName.length() - ".rule".length()));
    rule.put("pattern", "");
    for (String key : LIST_KEYS) {
      rule.put(key, new ArrayList<String>());
    }
    for (String raw : readLines(ruleFile)) {
      String line = raw.trim();
      int index = line.indexOf('=');
      if (line.isEmpty() || line.startsWith("#") || index < 0) {
        continue;
      }
      String key = line.substring(0, index).trim();
      String value = line.substring(index + 1).trim();
      if (LIST_KEYS.contains(key)) {
        rule.put(key, Arrays.stream(value.split(",")).map(String::trim).filter(s -> !s.isEmpty())
            .collect(Collectors.toList()));
      } else if (key.equals("pattern")) {
        rule.put("pattern", value);
      }
    }
    return rule;
  }

  static List<String> readAllowEntries(Path allowFile) {
    if (!Files.exists(allowFile)) {
      return List.of();
    }
    return readLines(allowFile).stream().map(String::trim)
        .filter(line -> !line.isEmpty() && !line.startsWith("#")).collect(Collectors.toList());
  }

  @SuppressWarnings("unchecked")
  static List<String> findViolatingFiles(Path repositoryRoot, Map<String, Object> rule) {
    Pattern pattern = Pattern.compile((String) rule.get("pattern"), Pattern.MULTILINE);
    List<String> paths = (List<String>) rule.get("paths");
    List<String> extensions = (List<String>) rule.get("extensions");
    List<String> excludes = (List<String>) rule.get("exclude");
    Set<String> violating = new TreeSet<>();
    for (String prefix : paths.isEmpty() ? List.of("") : paths) {
      Path base = repositoryRoot.resolve(prefix);
      List<Path> candidates = Files.isRegularFile(base) ? List.of(base) : Files.isDirectory(base) ? walk(base) : List.of();
      for (Path file : candidates) {
        String relative = repositoryRoot.relativize(file).toString().replace('\\', '/');
        if (relative.startsWith(ALWAYS_EXCLUDED_PREFIX) || excludes.stream().anyMatch(relative::startsWith)) {
          continue;
        }
        if (!extensions.isEmpty() && extensions.stream().noneMatch(relative::endsWith)) {
          continue;
        }
        if (pattern.matcher(readText(file)).find()) {
          violating.add(relative);
        }
      }
    }
    return new ArrayList<>(violating);
  }

  static List<Path> walk(Path directory) {
    List<Path> files = new ArrayList<>();
    try (Stream<Path> entries = Files.list(directory)) {
      for (Path entry : entries.sorted().collect(Collectors.toList())) {
        if (Files.isDirectory(entry)) {
          if (!SKIPPED_DIRECTORY_NAMES.contains(entry.getFileName().toString())) {
            files.addAll(walk(entry));
          }
        } else if (Files.isRegularFile(entry)) {
          files.add(entry);
        }
      }
    } catch (IOException exception) {
      throw new UncheckedIOException(exception);
    }
    return files;
  }

  static String readText(Path file) {
    try {
      return new String(Files.readAllBytes(file), StandardCharsets.UTF_8);
    } catch (IOException exception) {
      throw new UncheckedIOException(exception);
    }
  }

  static List<String> readLines(Path file) {
    return Arrays.asList(readText(file).split("\\r?\\n"));
  }
}
