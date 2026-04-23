import 'package:flutter/material.dart';
import 'package:fl_chart/fl_chart.dart';

// ─── Shared helpers ───────────────────────────────────────────────────────────

const _gridLine = FlLine(color: Color(0xFF1E3A5F), strokeWidth: 0.8);
const _noTitles = AxisTitles(sideTitles: SideTitles(showTitles: false));

TextStyle _axisStyle() =>
    const TextStyle(color: Color(0xFF475569), fontSize: 8);

Widget _chartCard(String title, String subtitle, Widget chart,
    {double height = 200}) {
  return Card(
    color: const Color(0xFF1E293B),
    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
    child: Padding(
      padding: const EdgeInsets.all(16),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(title,
            style: const TextStyle(
                color: Colors.white, fontWeight: FontWeight.bold, fontSize: 13)),
        if (subtitle.isNotEmpty)
          Padding(
            padding: const EdgeInsets.only(top: 2, bottom: 10),
            child: Text(subtitle,
                style:
                    const TextStyle(color: Color(0xFF64748B), fontSize: 10)),
          ),
        SizedBox(height: height, child: chart),
      ]),
    ),
  );
}

Widget _noData(String msg) => Center(
      child: Text(msg,
          style: const TextStyle(color: Color(0xFF475569), fontSize: 12)),
    );

// ─────────────────────────────────────────────────────────────────────────────
// ENERGY CHARTS
// ─────────────────────────────────────────────────────────────────────────────

/// Power Balance — Overlaid Area Chart (solar vs consumption).
class PowerBalanceChart extends StatelessWidget {
  final double avgPowerW;
  final double peakPowerW;
  final List<double> prediction;
  const PowerBalanceChart(
      {required this.avgPowerW,
      required this.peakPowerW,
      required this.prediction,
      super.key});

  @override
  Widget build(BuildContext context) {
    if (prediction.isEmpty) return _noData('No power data yet');
    final consumption = prediction;
    // Simulate solar as 70–90% of consumption
    final solar = consumption
        .asMap()
        .entries
        .map((e) => e.value * (0.7 + e.key * 0.03).clamp(0.0, 0.95))
        .toList();

    List<FlSpot> _spots(List<double> vals) =>
        vals.asMap().entries.map((e) => FlSpot(e.key.toDouble(), e.value)).toList();

    return _chartCard(
      'Power Balance',
      'Solar generation vs campus consumption',
      LineChart(LineChartData(
        gridData: FlGridData(
            show: true,
            getDrawingHorizontalLine: (_) => _gridLine,
            getDrawingVerticalLine: (_) => _gridLine),
        borderData: FlBorderData(show: false),
        titlesData: FlTitlesData(
          leftTitles: AxisTitles(
              sideTitles: SideTitles(
                  showTitles: true,
                  reservedSize: 40,
                  getTitlesWidget: (v, _) =>
                      Text(v.toStringAsFixed(0), style: _axisStyle()))),
          bottomTitles: _noTitles,
          topTitles: _noTitles,
          rightTitles: _noTitles,
        ),
        lineBarsData: [
          LineChartBarData(
            spots: _spots(solar),
            isCurved: true,
            color: const Color(0xFF4ADE80),
            barWidth: 2,
            belowBarData: BarAreaData(
                show: true,
                color: const Color(0xFF4ADE80).withOpacity(0.15)),
            dotData: const FlDotData(show: false),
          ),
          LineChartBarData(
            spots: _spots(consumption),
            isCurved: true,
            color: const Color(0xFFEF4444),
            barWidth: 2,
            belowBarData: BarAreaData(
                show: true,
                color: const Color(0xFFEF4444).withOpacity(0.1)),
            dotData: const FlDotData(show: false),
          ),
        ],
      )),
    );
  }
}

/// Solar Efficiency — Gauge + trend line.
class SolarEfficiencyChart extends StatelessWidget {
  final double avgPowerW;
  final double peakPowerW;
  const SolarEfficiencyChart(
      {required this.avgPowerW, required this.peakPowerW, super.key});

  @override
  Widget build(BuildContext context) {
    final efficiency =
        peakPowerW > 0 ? ((avgPowerW / peakPowerW) * 100).clamp(0, 100) : 0.0;
    final color = efficiency > 70
        ? const Color(0xFF4ADE80)
        : efficiency > 40
            ? const Color(0xFFFBBF24)
            : const Color(0xFFEF4444);

    return _chartCard(
      'Solar Efficiency',
      'Avg output vs peak capacity',
      Column(children: [
        const SizedBox(height: 8),
        SizedBox(
          height: 120,
          child: PieChart(PieChartData(
            startDegreeOffset: 180,
            sectionsSpace: 0,
            centerSpaceRadius: 40,
            sections: [
              PieChartSectionData(
                  value: efficiency.toDouble(),
                  color: color,
                  radius: 24,
                  showTitle: false),
              PieChartSectionData(
                  value: (100 - efficiency).toDouble(),
                  color: const Color(0xFF334155),
                  radius: 24,
                  showTitle: false),
            ],
          )),
        ),
        Text('${efficiency.toStringAsFixed(1)}%',
            style: TextStyle(
                color: color, fontSize: 24, fontWeight: FontWeight.bold)),
        Text('${avgPowerW.toStringAsFixed(0)} W avg  /  ${peakPowerW.toStringAsFixed(0)} W peak',
            style:
                const TextStyle(color: Color(0xFF64748B), fontSize: 10)),
      ]),
      height: 180,
    );
  }
}

/// Consumption Anomaly — Line with highlighted peak.
class ConsumptionAnomalyChart extends StatelessWidget {
  final List<double> prediction;
  final int faultCount;
  const ConsumptionAnomalyChart(
      {required this.prediction, required this.faultCount, super.key});

  @override
  Widget build(BuildContext context) {
    if (prediction.isEmpty) return _noData('No consumption data');
    final avg = prediction.reduce((a, b) => a + b) / prediction.length;
    final upper = avg * 1.3;

    final spots = prediction
        .asMap()
        .entries
        .map((e) => FlSpot(e.key.toDouble(), e.value))
        .toList();
    final upperBand = prediction
        .asMap()
        .entries
        .map((e) => FlSpot(e.key.toDouble(), upper))
        .toList();

    return _chartCard(
      'Consumption Anomaly',
      'Red dashed = +30% threshold band',
      LineChart(LineChartData(
        gridData: FlGridData(
            show: true,
            getDrawingHorizontalLine: (_) => _gridLine,
            getDrawingVerticalLine: (_) => _gridLine),
        borderData: FlBorderData(show: false),
        titlesData: FlTitlesData(
          leftTitles: AxisTitles(
              sideTitles: SideTitles(
                  showTitles: true,
                  reservedSize: 40,
                  getTitlesWidget: (v, _) =>
                      Text(v.toStringAsFixed(0), style: _axisStyle()))),
          bottomTitles: _noTitles,
          topTitles: _noTitles,
          rightTitles: _noTitles,
        ),
        lineBarsData: [
          LineChartBarData(
            spots: spots,
            isCurved: true,
            color: const Color(0xFFFBBF24),
            barWidth: 2,
            dotData: const FlDotData(show: false),
            belowBarData: BarAreaData(
                show: true,
                color: const Color(0xFFFBBF24).withOpacity(0.1)),
          ),
          LineChartBarData(
            spots: upperBand,
            isCurved: false,
            color: const Color(0xFFEF4444),
            barWidth: 1.5,
            dashArray: [5, 4],
            dotData: const FlDotData(show: false),
          ),
        ],
      )),
    );
  }
}

/// Grid Stability — Bar chart for voltage variance.
class GridStabilityChart extends StatelessWidget {
  final double avgPowerW;
  final int faultCount;
  const GridStabilityChart(
      {required this.avgPowerW, required this.faultCount, super.key});

  @override
  Widget build(BuildContext context) {
    // Simulate voltage readings around nominal 230V
    final voltages = List.generate(
        8, (i) => 225.0 + (i % 3 == 0 ? -8 : i % 2 == 0 ? 6 : 2));

    final bars = voltages
        .asMap()
        .entries
        .map((e) {
          final v = e.value;
          final isNominal = v >= 220 && v <= 240;
          return BarChartGroupData(x: e.key, barRods: [
            BarChartRodData(
              toY: v,
              fromY: 200,
              color: isNominal
                  ? const Color(0xFF4ADE80)
                  : const Color(0xFFEF4444),
              width: 14,
              borderRadius: BorderRadius.circular(4),
            )
          ]);
        })
        .toList();

    return _chartCard(
      'Grid Stability',
      'Voltage readings — green = nominal (220–240V)',
      BarChart(BarChartData(
        barGroups: bars,
        minY: 200,
        maxY: 250,
        gridData: FlGridData(
            show: true,
            getDrawingHorizontalLine: (_) => _gridLine,
            getDrawingVerticalLine: (_) => _gridLine),
        borderData: FlBorderData(show: false),
        titlesData: FlTitlesData(
          leftTitles: AxisTitles(
              sideTitles: SideTitles(
                  showTitles: true,
                  reservedSize: 36,
                  getTitlesWidget: (v, _) =>
                      Text(v.toStringAsFixed(0), style: _axisStyle()))),
          bottomTitles: _noTitles,
          topTitles: _noTitles,
          rightTitles: _noTitles,
        ),
      )),
    );
  }
}

/// Device Schedule — horizontal bars showing on/off schedule.
class DeviceScheduleChart extends StatelessWidget {
  final int faultCount;
  const DeviceScheduleChart({required this.faultCount, super.key});

  @override
  Widget build(BuildContext context) {
    final devices = ['Streetlights', 'AC Units', 'Solar Inv.'];
    final colors = [
      const Color(0xFFFBBF24),
      const Color(0xFF38BDF8),
      const Color(0xFF4ADE80),
    ];
    final schedules = [
      [false, false, false, false, true, true, true, true], // night on
      [true, true, true, true, true, false, false, false],  // day on
      [false, true, true, true, true, true, false, false],  // daylight
    ];

    return _chartCard(
      'Device Schedule',
      'Hourly ON/OFF state (6h blocks)',
      Column(
        mainAxisAlignment: MainAxisAlignment.spaceEvenly,
        children: devices.asMap().entries.map((dev) {
          return Padding(
            padding: const EdgeInsets.symmetric(vertical: 4),
            child: Row(children: [
              SizedBox(
                width: 72,
                child: Text(dev.value,
                    style: const TextStyle(
                        color: Color(0xFF94A3B8), fontSize: 9)),
              ),
              ...schedules[dev.key].map((on) => Expanded(
                    child: Container(
                      height: 20,
                      margin: const EdgeInsets.symmetric(horizontal: 1),
                      decoration: BoxDecoration(
                        color: on
                            ? colors[dev.key].withOpacity(0.8)
                            : const Color(0xFF334155),
                        borderRadius: BorderRadius.circular(3),
                      ),
                    ),
                  )),
            ]),
          );
        }).toList(),
      ),
      height: 150,
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// EHS CHARTS
// ─────────────────────────────────────────────────────────────────────────────

/// Air Quality — Radar chart for PM2.5, CO2, NO2, O3.
class AirQualityRadarChart extends StatelessWidget {
  final double pm25;
  final double co2;
  const AirQualityRadarChart({required this.pm25, required this.co2, super.key});

  @override
  Widget build(BuildContext context) {
    // Normalise each metric to 0–100 scale against its safe limit
    final pm25Pct = (pm25 / 50 * 100).clamp(0, 100);
    final co2Pct  = (co2 / 1000 * 100).clamp(0, 100);
    const no2Pct  = 30.0; // default moderate
    const o3Pct   = 25.0;

    final dataEntries = [pm25Pct, co2Pct, no2Pct, o3Pct]
        .map((v) => RadarEntry(value: v.toDouble()))
        .toList();
    final safeEntries = List.generate(4, (_) => const RadarEntry(value: 60));

    return _chartCard(
      'Air Quality Radar',
      'PM2.5 | CO2 | NO2 | O3  —  red zone = unsafe',
      RadarChart(RadarChartData(
        radarShape: RadarShape.polygon,
        tickCount: 4,
        ticksTextStyle:
            const TextStyle(color: Color(0xFF334155), fontSize: 8),
        gridBorderData:
            const BorderSide(color: Color(0xFF334155), width: 0.8),
        radarBorderData:
            const BorderSide(color: Color(0xFF475569), width: 1),
        titleTextStyle:
            const TextStyle(color: Color(0xFF94A3B8), fontSize: 9),
        getTitle: (idx, _) {
          const labels = ['PM2.5', 'CO2', 'NO2', 'O3'];
          return RadarChartTitle(text: labels[idx]);
        },
        dataSets: [
          RadarDataSet(
            dataEntries: safeEntries,
            fillColor: const Color(0xFF4ADE80).withOpacity(0.08),
            borderColor: const Color(0xFF4ADE80).withOpacity(0.4),
            borderWidth: 1.5,
            entryRadius: 0,
          ),
          RadarDataSet(
            dataEntries: dataEntries,
            fillColor: const Color(0xFFEF4444).withOpacity(0.2),
            borderColor: const Color(0xFFEF4444),
            borderWidth: 2,
            entryRadius: 3,
          ),
        ],
      )),
    );
  }
}

/// Indoor Comfort — Temperature vs Humidity scatter.
class IndoorComfortChart extends StatelessWidget {
  final double pm25;
  final double co2;
  const IndoorComfortChart({required this.pm25, required this.co2, super.key});

  @override
  Widget build(BuildContext context) {
    // Simulate comfort scatter points
    final points = [
      FlSpot(22, 50), FlSpot(24, 55), FlSpot(26, 60),
      FlSpot(28, 65), FlSpot(20, 45), FlSpot(30, 70),
    ];

    return _chartCard(
      'Indoor Comfort (ASHRAE)',
      'Temperature (°C) vs Humidity (%) — green band = comfort zone',
      ScatterChart(ScatterChartData(
        scatterSpots: points.map<ScatterSpot>((p) {
          final inZone = p.x >= 20 && p.x <= 26 && p.y >= 40 && p.y <= 60;
          return ScatterSpot(
            p.x.toDouble(),
            p.y.toDouble(),
            dotPainter: FlDotCirclePainter(
              radius: 6,
              color: inZone ? const Color(0xFF4ADE80) : const Color(0xFFEF4444),
            ),
          );
        }).toList(),
        minX: 16, maxX: 34, minY: 30, maxY: 80,
        gridData: FlGridData(
            show: true,
            getDrawingHorizontalLine: (_) => _gridLine,
            getDrawingVerticalLine: (_) => _gridLine),
        borderData: FlBorderData(show: false),
        titlesData: FlTitlesData(
          leftTitles: AxisTitles(
              sideTitles: SideTitles(
                  showTitles: true,
                  reservedSize: 36,
                  getTitlesWidget: (v, _) =>
                      Text('${v.toInt()}%', style: _axisStyle()))),
          bottomTitles: AxisTitles(
              sideTitles: SideTitles(
                  showTitles: true,
                  reservedSize: 18,
                  getTitlesWidget: (v, _) =>
                      Text('${v.toInt()}°', style: _axisStyle()))),
          topTitles: _noTitles,
          rightTitles: _noTitles,
        ),
      )),
    );
  }
}

/// Water Quality — Multi-line chart with pH thresholds.
class WaterQualityChart extends StatelessWidget {
  final double phAvg;
  final int events;
  final List<double> prediction;
  const WaterQualityChart(
      {required this.phAvg,
      required this.events,
      required this.prediction,
      super.key});

  @override
  Widget build(BuildContext context) {
    if (prediction.isEmpty) return _noData('No water quality data');

    final phSpots = prediction
        .asMap()
        .entries
        .map((e) => FlSpot(e.key.toDouble(), e.value))
        .toList();
    final upperLimit =
        prediction.map((v) => FlSpot(prediction.indexOf(v).toDouble(), 8.5)).toList();
    final lowerLimit =
        prediction.map((v) => FlSpot(prediction.indexOf(v).toDouble(), 6.5)).toList();

    return _chartCard(
      'Water Quality — pH',
      'Dashed lines = WHO safe range (6.5 – 8.5)',
      LineChart(LineChartData(
        minY: 5.5, maxY: 9.5,
        gridData: FlGridData(
            show: true,
            getDrawingHorizontalLine: (_) => _gridLine,
            getDrawingVerticalLine: (_) => _gridLine),
        borderData: FlBorderData(show: false),
        titlesData: FlTitlesData(
          leftTitles: AxisTitles(
              sideTitles: SideTitles(
                  showTitles: true,
                  reservedSize: 36,
                  getTitlesWidget: (v, _) =>
                      Text(v.toStringAsFixed(1), style: _axisStyle()))),
          bottomTitles: _noTitles,
          topTitles: _noTitles,
          rightTitles: _noTitles,
        ),
        lineBarsData: [
          LineChartBarData(
            spots: phSpots,
            isCurved: true,
            color: const Color(0xFF38BDF8),
            barWidth: 2.5,
            dotData: const FlDotData(show: false),
            belowBarData: BarAreaData(
                show: true,
                color: const Color(0xFF38BDF8).withOpacity(0.1)),
          ),
          LineChartBarData(
            spots: upperLimit,
            color: const Color(0xFFEF4444),
            barWidth: 1,
            dashArray: [6, 4],
            dotData: const FlDotData(show: false),
          ),
          LineChartBarData(
            spots: lowerLimit,
            color: const Color(0xFFF97316),
            barWidth: 1,
            dashArray: [6, 4],
            dotData: const FlDotData(show: false),
          ),
        ],
      )),
    );
  }
}

/// Water Safety — Bar chart (flow proxy).
class WaterSafetyChart extends StatelessWidget {
  final int events;
  const WaterSafetyChart({required this.events, super.key});

  @override
  Widget build(BuildContext context) {
    final flows = [12.0, 14.0, 11.0, 9.0, 2.0, 1.0, 13.0, 15.0];
    final pressures = [3.2, 3.1, 3.0, 2.8, 0.2, 0.1, 3.3, 3.4];

    final bars = flows.asMap().entries.map((e) {
      final burst = flows[e.key] > 10 && pressures[e.key] < 1.0;
      return BarChartGroupData(x: e.key, barRods: [
        BarChartRodData(
          toY: e.value,
          color: burst ? const Color(0xFFEF4444) : const Color(0xFF38BDF8),
          width: 14,
          borderRadius: BorderRadius.circular(4),
        )
      ]);
    }).toList();

    return _chartCard(
      'Water Safety — Flow Rate',
      'Red = burst signature (high flow + low pressure)',
      BarChart(BarChartData(
        barGroups: bars,
        gridData: FlGridData(
            show: true,
            getDrawingHorizontalLine: (_) => _gridLine,
            getDrawingVerticalLine: (_) => _gridLine),
        borderData: FlBorderData(show: false),
        titlesData: FlTitlesData(
          leftTitles: AxisTitles(
              sideTitles: SideTitles(
                  showTitles: true,
                  reservedSize: 36,
                  getTitlesWidget: (v, _) =>
                      Text('${v.toInt()}L', style: _axisStyle()))),
          bottomTitles: _noTitles,
          topTitles: _noTitles,
          rightTitles: _noTitles,
        ),
      )),
    );
  }
}

/// Equipment Health — Step chart (pump on/off) + flow overlay.
class EquipmentHealthChart extends StatelessWidget {
  final int events;
  const EquipmentHealthChart({required this.events, super.key});

  @override
  Widget build(BuildContext context) {
    // pump state 1=ON 0=OFF
    final pumpState = [0.0, 1.0, 1.0, 1.0, 1.0, 0.0, 0.0, 1.0];
    // flow — dry running when pump ON but flow=0
    final flowRate  = [0.0, 0.0, 0.0, 8.0, 9.0, 0.0, 0.0, 7.5];

    List<FlSpot> _s(List<double> v) =>
        v.asMap().entries.map((e) => FlSpot(e.key.toDouble(), e.value)).toList();

    return _chartCard(
      'Equipment Health',
      'Yellow=Pump ON, Blue=Flow — gap = Dry Running ⚠️',
      LineChart(LineChartData(
        minY: -0.5, maxY: 11,
        gridData: FlGridData(
            show: true,
            getDrawingHorizontalLine: (_) => _gridLine,
            getDrawingVerticalLine: (_) => _gridLine),
        borderData: FlBorderData(show: false),
        titlesData: FlTitlesData(
          leftTitles: AxisTitles(
              sideTitles: SideTitles(
                  showTitles: true,
                  reservedSize: 36,
                  getTitlesWidget: (v, _) =>
                      Text(v.toStringAsFixed(0), style: _axisStyle()))),
          bottomTitles: _noTitles,
          topTitles: _noTitles,
          rightTitles: _noTitles,
        ),
        lineBarsData: [
          LineChartBarData(
            spots: _s(pumpState.map((v) => v * 10).toList()),
            isStepLineChart: true,
            color: const Color(0xFFFBBF24),
            barWidth: 2,
            dotData: const FlDotData(show: false),
            belowBarData: BarAreaData(
                show: true,
                color: const Color(0xFFFBBF24).withOpacity(0.08)),
          ),
          LineChartBarData(
            spots: _s(flowRate),
            isCurved: true,
            color: const Color(0xFF38BDF8),
            barWidth: 2,
            dotData: const FlDotData(show: false),
          ),
        ],
      )),
    );
  }
}
