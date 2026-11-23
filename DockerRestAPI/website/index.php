<?php
// Consumer for the brevet times REST service.
// The page calls the "api" container by its docker-compose service name,
// so the request is made server side, container to container.

const API_BASE = 'http://api';
const LISTS = [
    'listAll'       => 'Open and close times',
    'listOpenOnly'  => 'Open times only',
    'listCloseOnly' => 'Close times only',
];
const FORMATS = ['json' => 'JSON', 'csv' => 'CSV'];

function h($s) { return htmlspecialchars((string) $s, ENT_QUOTES, 'UTF-8'); }

// Only accept known values, so the URL we build is always one of ours.
$list   = array_key_exists($_GET['list'] ?? '', LISTS) ? $_GET['list'] : 'listAll';
$format = array_key_exists($_GET['format'] ?? '', FORMATS) ? $_GET['format'] : 'json';
$top    = trim($_GET['top'] ?? '');

$url = API_BASE . '/' . $list . '/' . $format;
if ($top !== '') {
    $url .= '?top=' . urlencode($top);
}

// ignore_errors returns the body for 4xx/5xx too, so we can show the API's message.
$context = stream_context_create(['http' => ['ignore_errors' => true, 'timeout' => 5]]);
$body = @file_get_contents($url, false, $context);
$status = 0;
if (isset($http_response_header[0]) && preg_match('/\s(\d{3})\s/', $http_response_header[0], $m)) {
    $status = (int) $m[1];
}

$error = null;
$brevets = null;   // JSON result
$rows = null;      // CSV result
if ($body === false) {
    $error = 'Could not reach the API service.';
} elseif ($status !== 200) {
    $decoded = json_decode($body, true);
    $error = $decoded['error'] ?? $decoded['message'] ?? "The API returned status $status.";
} elseif ($format === 'json') {
    $brevets = json_decode($body, true)['brevets'] ?? [];
} else {
    $lines = array_filter(explode("\n", $body), 'strlen');
    $rows = array_map(fn($l) => str_getcsv($l, ',', '"', ''), $lines);
}
$fields = $list === 'listAll' ? ['open', 'close'] : ($list === 'listOpenOnly' ? ['open'] : ['close']);
?>
<!DOCTYPE html>
<html>
<head>
  <title>Brevet Times</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="stylesheet"
   href="https://maxcdn.bootstrapcdn.com/bootstrap/3.3.5/css/bootstrap.min.css">
</head>
<body>
<div class="container">
  <h1>Brevet Times</h1>
  <p>Control times saved by the calculator, read from the REST service.</p>

  <form method="get" class="form-inline" style="margin-bottom: 1.5em">
    <div class="form-group">
      <label for="list">Show</label>
      <select name="list" id="list" class="form-control">
        <?php foreach (LISTS as $value => $label): ?>
          <option value="<?= h($value) ?>" <?= $value === $list ? 'selected' : '' ?>><?= h($label) ?></option>
        <?php endforeach; ?>
      </select>
    </div>
    <div class="form-group">
      <label for="format">as</label>
      <select name="format" id="format" class="form-control">
        <?php foreach (FORMATS as $value => $label): ?>
          <option value="<?= h($value) ?>" <?= $value === $format ? 'selected' : '' ?>><?= h($label) ?></option>
        <?php endforeach; ?>
      </select>
    </div>
    <div class="form-group">
      <label for="top">Top</label>
      <input type="number" min="1" name="top" id="top" class="form-control"
             style="width: 7em" placeholder="all" value="<?= h($top) ?>">
    </div>
    <button type="submit" class="btn btn-primary">Show</button>
  </form>

  <p><small>Request: <code><?= h('/' . $list . '/' . $format . ($top !== '' ? '?top=' . $top : '')) ?></code></small></p>

  <?php if ($error !== null): ?>
    <div class="alert alert-danger"><?= h($error) ?></div>

  <?php elseif ($brevets !== null): ?>
    <?php if (count($brevets) === 0): ?>
      <div class="alert alert-info">Nothing has been saved yet.</div>
    <?php endif; ?>
    <?php foreach ($brevets as $b): ?>
      <h3><?= h($b['distance']) ?> km brevet
        <small>starts <?= h($b['begin_date']) ?> <?= h($b['begin_time']) ?></small></h3>
      <table class="table table-condensed table-striped">
        <tr>
          <th>Km</th><th>Miles</th><th>Location</th>
          <?php foreach ($fields as $f): ?><th><?= h(ucfirst($f)) ?></th><?php endforeach; ?>
        </tr>
        <?php foreach ($b['controls'] as $c): ?>
          <tr>
            <td><?= h($c['km']) ?></td>
            <td><?= h($c['mi']) ?></td>
            <td><?= h($c['location'] ?? '') ?></td>
            <?php foreach ($fields as $f): ?><td><?= h($c[$f]) ?></td><?php endforeach; ?>
          </tr>
        <?php endforeach; ?>
      </table>
    <?php endforeach; ?>

  <?php else: ?>
    <?php if (count($rows) <= 1): ?>
      <div class="alert alert-info">Nothing has been saved yet.</div>
    <?php else: ?>
      <table class="table table-condensed table-striped">
        <tr><?php foreach ($rows[0] as $col): ?><th><?= h(basename($col)) ?></th><?php endforeach; ?></tr>
        <?php foreach (array_slice($rows, 1) as $row): ?>
          <tr><?php foreach ($row as $cell): ?><td><?= h($cell) ?></td><?php endforeach; ?></tr>
        <?php endforeach; ?>
      </table>
    <?php endif; ?>
  <?php endif; ?>

  <?php if ($body !== false): ?>
    <h4>Raw response</h4>
    <pre><?= h($body) ?></pre>
  <?php endif; ?>
</div>
</body>
</html>
