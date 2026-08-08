// AssemblyPlatform.cs — одна експериментальна площадка: рука + деталь +
// точка монтажу. Проганяє ОДНУ особину: фази руху, захоплення,
// встановлення, вимірювання метрик (GENOME_SPEC.md §5).
using System.Collections.Generic;
using UnityEngine;

namespace GAExperiment
{
    public class AssemblyPlatform : MonoBehaviour
    {
        public bool Finished { get; private set; } = true;
        public IndividualResult Result { get; private set; }

        private BuiltArm _arm;
        private DecodedGenome _genome;
        private int _individualId;

        private Rigidbody _part;
        private Transform _mount;
        private FixedJoint _grasp;

        private float _t;                  // час прогону, с
        private int _phase;                // 0..3, 4 = settle
        private float _phaseT;
        private float[] _fromPose = new float[GenomeSpec.Links];
        private readonly float[] _jointWork = new float[GenomeSpec.Links];
        private float[] _prevJointPos = new float[GenomeSpec.Links];
        private int _collisions;
        private bool _grasped, _success;
        private float _bestPrecision;
        private float _bestApproach;   // мін. відстань ефектор↔деталь за прогін

        // ДІАГНОСТИЧНЕ (сесія 2026-08, path_efficiency): реальний шлях
        // деталі поки вона захоплена, vs пряма між точкою захвату і
        // фінальною позицією. НЕ впливає на success/fitness — лише
        // логується для аналізу "тягання по підлозі" / зайвих рухів.
        private Vector3 _graspPos;
        private Vector3 _partPrevPos;
        private float _pathLength;

        // ── Статичні об'єкти площадки (створюються один раз) ────────────
        public void Init()
        {
            var floor = MakeStatic("Floor", new Vector3(0f, -0.05f, 0f),
                       new Vector3(3f, 0.1f, 3f));
            ExperimentOrchestrator.Paint(floor, ExperimentOrchestrator.FloorColor);
            var stand = MakeStatic("PartStand",
                       GenomeSpec.PartPickupPos - new Vector3(0f, 0.115f, 0f),
                       new Vector3(0.08f, 0.17f, 0.08f));
            ExperimentOrchestrator.Paint(stand, ExperimentOrchestrator.StandColor);
            var mount = MakeStatic("Mount",
                       GenomeSpec.MountPos - new Vector3(0f, 0.02f, 0f),
                       new Vector3(0.10f, 0.04f, 0.10f));
            ExperimentOrchestrator.Paint(mount, ExperimentOrchestrator.MountColor);
            _mount = mount.transform;
        }

        private GameObject MakeStatic(string n, Vector3 localPos, Vector3 size)
        {
            var go = GameObject.CreatePrimitive(PrimitiveType.Cube);
            go.name = n;
            go.transform.SetParent(transform, false);
            go.transform.localPosition = localPos;
            go.transform.localScale = size;
            return go;
        }

        // ── Запуск особини ───────────────────────────────────────────────
        public void Run(Genome g)
        {
            Cleanup();
            _individualId = g.IndividualId;
            _genome = DecodedGenome.Decode(g);
            _arm = ArmBuilder.Build(_genome, transform, OnLinkCollision);

            var partGo = GameObject.CreatePrimitive(PrimitiveType.Cube);
            partGo.name = "Part";
            partGo.transform.SetParent(transform, false);
            partGo.transform.localScale = Vector3.one * 0.04f;
            partGo.transform.localPosition = GenomeSpec.PartPickupPos;
            ExperimentOrchestrator.Paint(partGo, ExperimentOrchestrator.PartColor);
            _part = partGo.AddComponent<Rigidbody>();
            _part.mass = GenomeSpec.PartMass;

            _t = 0f; _phase = 0; _phaseT = 0f;
            _collisions = 0; _grasped = false; _success = false;
            _bestPrecision = float.MaxValue;
            _bestApproach = float.MaxValue;
            _pathLength = 0f; _graspPos = Vector3.zero; _partPrevPos = Vector3.zero;
            for (int i = 0; i < GenomeSpec.Links; i++)
            { _jointWork[i] = 0f; _fromPose[i] = 0f; _prevJointPos[i] = 0f; }
            Finished = false;
        }

        private void FixedUpdate()
        {
            if (Finished) return;
            float dt = Time.fixedDeltaTime;
            _t += dt; _phaseT += dt;

            // Запобіжник "фізичного вибуху": NaN або відліт за 5 м → фініш
            Vector3 effLocal = transform.InverseTransformPoint(_arm.Effector.position);
            if (float.IsNaN(effLocal.x) || effLocal.magnitude > 5f)
            { Finish(); return; }

            // Ізоляція площадок (Р9): деталь покинула зону 3 м → фініш,
            // щоб вона не докотилась до сусіднього експерименту
            Vector3 partLocal = transform.InverseTransformPoint(_part.position);
            if (float.IsNaN(partLocal.x) || partLocal.magnitude > 3f)
            { Finish(); return; }

            DrivePhases();
            MeasureEnergy();
            TryGrasp();
            TrackPath();
            TryInstall();

            float cycle = Sum(GenomeSpec.PhaseDurations);
            if (_success || _t >= cycle + GenomeSpec.SettleAfterCycle
                         || _t >= GenomeSpec.PlatformTimeLimit)
                Finish();
        }

        private void DrivePhases()
        {
            if (_phase >= GenomeSpec.Phases) return;
            float dur = GenomeSpec.PhaseDurations[_phase];
            float s = Mathf.Clamp01(_phaseT / dur);
            for (int i = 0; i < GenomeSpec.Links; i++)
            {
                float target = Mathf.Lerp(_fromPose[i],
                                          _genome.PhaseTargets[_phase, i], s);
                var d = _arm.Joints[i].xDrive;
                d.target = target;
                _arm.Joints[i].xDrive = d;
            }
            if (_phaseT >= dur)
            {
                for (int i = 0; i < GenomeSpec.Links; i++)
                    _fromPose[i] = _genome.PhaseTargets[_phase, i];
                _phase++; _phaseT = 0f;
            }
        }

        // E += Σ|τ_i · Δθ_i|. jointForce в Unity — це сили КОРИСТУВАЧА
        // (читається нулем), тому момент драйва оцінюємо його ж моделлю:
        // τ = k·(θ_target − θ) − c·θ̇, |τ| ≤ forceLimit — саме це
        // прикладає PhysX всередині.
        private void MeasureEnergy()
        {
            for (int i = 0; i < GenomeSpec.Links; i++)
            {
                var ab = _arm.Joints[i];
                if (ab.jointPosition.dofCount < 1) continue;
                float pos = ab.jointPosition[0];              // рад
                float vel = ab.jointVelocity.dofCount > 0 ? ab.jointVelocity[0] : 0f;
                float targetRad = ab.xDrive.target * Mathf.Deg2Rad;
                float tau = GenomeSpec.DriveStiffness * (targetRad - pos)
                          - GenomeSpec.DriveDamping * vel;
                tau = Mathf.Clamp(tau, -GenomeSpec.DriveForceLimit,
                                        GenomeSpec.DriveForceLimit);
                _jointWork[i] += Mathf.Abs(tau * (pos - _prevJointPos[i]));
                _prevJointPos[i] = pos;
            }
        }

        private void TryGrasp()
        {
            if (_grasped) return;
            float dist = Vector3.Distance(_arm.Effector.position, _part.position);
            _bestApproach = Mathf.Min(_bestApproach, dist); // градієнт "наблизився"
            if (dist > GenomeSpec.CurrentGraspRadius) return;
            // Реалізм грипера: захоплення лише при контрольованому підході,
            // а не "на прольоті" — відносна швидкість ефектора і деталі
            var lastLink = _arm.Joints[GenomeSpec.Links - 1];
            float relSpeed = (lastLink.linearVelocity - _part.linearVelocity).magnitude;
            if (relSpeed > 0.5f) return;
            _grasp = _part.gameObject.AddComponent<FixedJoint>();
            _grasp.connectedArticulationBody = lastLink;
            _grasped = true;
            // Старт трекінгу шляху — з фактичної точки захвату
            _graspPos = _part.position;
            _partPrevPos = _part.position;
            _pathLength = 0f;
        }

        // Накопичує реальну довжину шляху деталі, поки вона захоплена.
        // Викликається щокроку ПІСЛЯ TryGrasp() (щоб рух у крок захвату
        // ще не рахувався зайвим) і ДО TryInstall().
        private void TrackPath()
        {
            if (!_grasped) return;
            _pathLength += Vector3.Distance(_part.position, _partPrevPos);
            _partPrevPos = _part.position;
        }

        private void TryInstall()
        {
            if (!_grasped || _success) return;
            float err = Vector3.Distance(_part.position,
                                         _mount.position + Vector3.up * 0.04f);
            _bestPrecision = Mathf.Min(_bestPrecision, err);
            // Встановлення зараховується лише у фазі 4 (індекс 3) чи пізніше
            if (_phase >= 3 && err <= GenomeSpec.CurrentSuccessTolerance)
            {
                _success = true;
                if (_grasp != null) Destroy(_grasp);
            }
        }

        private void OnLinkCollision(Collision c)
        {
            if (Finished) return;
            // Контакт із деталлю — не порушення (це і є робота)
            if (_part != null && c.rigidbody == _part) return;
            _collisions++;
        }

        private void Finish()
        {
            Finished = true;
            float mean = 0f, mx = 0f;
            foreach (var w in _jointWork) { mean += w; mx = Mathf.Max(mx, w); }
            mean /= GenomeSpec.Links;
            float sd = 0f;
            foreach (var w in _jointWork) sd += (w - mean) * (w - mean);
            sd = Mathf.Sqrt(sd / GenomeSpec.Links);

            float prec = _grasped
                ? (_bestPrecision == float.MaxValue ? 1f : _bestPrecision)
                : 1f + (_bestApproach == float.MaxValue
                        ? Vector3.Distance(_arm.Effector.position, _part.position)
                        : _bestApproach); // градієнт за всю траєкторію, не фінал
            if (float.IsNaN(prec) || prec > 10f) prec = 10f; // кліп вибухів

            // path_efficiency: 1.0 = ідеально пряма; > 1.0 = зайві рухи.
            // 0.0, якщо не захоплено (нема що міряти). Поріг 0.01 м у
            // знаменнику — захист від вибуху при майже нульовому
            // фактичному переміщенні деталі.
            float pathEff = 0f;
            if (_grasped)
            {
                float straight = Vector3.Distance(_graspPos, _part.position);
                pathEff = _pathLength / Mathf.Max(straight, 0.01f);
                if (float.IsNaN(pathEff) || float.IsInfinity(pathEff)) pathEff = 0f;
            }

            Result = new IndividualResult
            {
                IndividualId = _individualId,
                AssemblyTime = _success ? _t : GenomeSpec.PlatformTimeLimit,
                Energy = Sum(_jointWork),
                WearCv = mean > 1e-6f ? sd / mean : 10f,
                WearMax = mx,
                JointWork = new List<float>(_jointWork),
                PrecisionError = prec,
                Collisions = _collisions,
                Success = _success,
                PathEfficiency = pathEff,
                Fitness = 0f // рахує сервер
            };
        }

        public void Cleanup()
        {
            if (_arm != null) Destroy(_arm.GO);
            if (_part != null) Destroy(_part.gameObject);
            _arm = null; _part = null;
        }

        private static float Sum(IReadOnlyList<float> a)
        { float s = 0f; for (int i = 0; i < a.Count; i++) s += a[i]; return s; }
        private static float Sum(float[] a)
        { float s = 0f; foreach (var x in a) s += x; return s; }
    }
}
