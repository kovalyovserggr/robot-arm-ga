// ArmBuilder.cs — будує 6R-маніпулятор з DH-параметрів у рантаймі.
//
// Конвенція (GENOME_SPEC.md §1, модифікована DH):
//   кадр ланки i відносно i-1:  зсув x на a_i → поворот навколо x на α_i
//   → зсув z на d_i → суглоб обертає тіло навколо ЛОКАЛЬНОЇ Z.
//
// Технічна деталь Unity: твіст-вісь ArticulationBody — це X якірної
// системи. Тому anchorRotation = Euler(0,-90,0), що суміщає якірний X
// з локальним Z тіла → обертання йде навколо Z, як вимагає DH.
using System.Collections.Generic;
using UnityEngine;

namespace GAExperiment
{
    public class BuiltArm
    {
        public ArticulationBody Root;                       // нерухома база
        public List<ArticulationBody> Joints = new();       // 6 суглобів
        public Transform Effector;                          // кінчик інструмента
        public GameObject GO;
    }

    public static class ArmBuilder
    {
        public static BuiltArm Build(DecodedGenome g, Transform platform,
                                     LinkCollisionReporter.Handler onCollision)
        {
            var arm = new BuiltArm();
            arm.GO = new GameObject("Arm");
            arm.GO.transform.SetParent(platform, false);

            // База: п'єдестал 0.10 м; локальний Z бази дивиться вгору (світовий Y),
            // щоб перший суглоб за DH крутився навколо вертикалі.
            var baseGo = new GameObject("Base");
            baseGo.transform.SetParent(arm.GO.transform, false);
            baseGo.transform.localPosition = new Vector3(0f, 0.10f, 0f);
            baseGo.transform.localRotation = Quaternion.Euler(-90f, 0f, 0f);
            arm.Root = baseGo.AddComponent<ArticulationBody>();
            arm.Root.immovable = true;

            Transform parent = baseGo.transform;
            for (int i = 0; i < GenomeSpec.Links; i++)
            {
                var link = new GameObject($"Link{i + 1}");
                link.transform.SetParent(parent, false);

                // Фіксований DH-трансформ кадру ланки відносно попередньої
                Quaternion rx = Quaternion.AngleAxis(g.Alpha[i], Vector3.right);
                link.transform.localRotation = rx;
                link.transform.localPosition =
                    new Vector3(g.A[i], 0f, 0f) + rx * new Vector3(0f, 0f, g.D[i]);

                // Візуал + колайдери сегментів a (по x батька) і d (по z кадру)
                AddSegment(parent, Vector3.right, g.A[i], $"SegA{i + 1}", onCollision);
                AddSegment(link.transform.parent, rx * Vector3.forward, g.D[i],
                           $"SegD{i + 1}", onCollision, new Vector3(g.A[i], 0f, 0f));

                var ab = link.AddComponent<ArticulationBody>();
                ab.jointType = ArticulationJointType.RevoluteJoint;
                ab.anchorRotation = Quaternion.Euler(0f, -90f, 0f); // твіст X → локальний Z
                ab.mass = Mathf.Max(GenomeSpec.LinkMinMass,
                                    GenomeSpec.LinkDensity * (g.A[i] + g.D[i]));
                ab.twistLock = ArticulationDofLock.LimitedMotion;
                var drive = ab.xDrive;
                drive.lowerLimit = -GenomeSpec.JointLimitDeg;
                drive.upperLimit =  GenomeSpec.JointLimitDeg;
                drive.stiffness  = GenomeSpec.DriveStiffness;
                drive.damping    = GenomeSpec.DriveDamping;
                drive.forceLimit = GenomeSpec.DriveForceLimit;
                drive.target = 0f;
                ab.xDrive = drive;

                arm.Joints.Add(ab);
                parent = link.transform;
            }

            // Ефектор: інструмент уздовж локального X останньої ланки
            AddSegment(parent, Vector3.right, GenomeSpec.ToolLength, "Tool", onCollision);
            var eff = new GameObject("Effector");
            eff.transform.SetParent(parent, false);
            eff.transform.localPosition = new Vector3(GenomeSpec.ToolLength, 0f, 0f);
            arm.Effector = eff.transform;

            IgnoreAdjacentCollisions(arm);
            return arm;
        }

        // Циліндричний сегмент довжиною len уздовж dir від offset (у кадрі parent)
        private static void AddSegment(Transform parent, Vector3 dir, float len,
                                       string name, LinkCollisionReporter.Handler onCol,
                                       Vector3 offset = default)
        {
            if (len < 0.015f) return; // нульові ланки — без геометрії
            var seg = GameObject.CreatePrimitive(PrimitiveType.Capsule);
            seg.name = name;
            Object.Destroy(seg.GetComponent<CapsuleCollider>());
            seg.transform.SetParent(parent, false);
            seg.transform.localPosition = offset + dir * (len * 0.5f);
            seg.transform.localRotation = Quaternion.FromToRotation(Vector3.up, dir);
            seg.transform.localScale = new Vector3(GenomeSpec.LinkRadius * 2f,
                                                   len * 0.5f,
                                                   GenomeSpec.LinkRadius * 2f);
            ExperimentOrchestrator.Paint(seg, name == "Tool"
                ? ExperimentOrchestrator.ToolColor
                : ExperimentOrchestrator.ArmColor);
            var col = seg.AddComponent<CapsuleCollider>();
            col.direction = 1; // Y капсули
            var rep = seg.AddComponent<LinkCollisionReporter>();
            rep.OnHit = onCol;
        }

        private static void IgnoreAdjacentCollisions(BuiltArm arm)
        {
            var all = arm.GO.GetComponentsInChildren<Collider>();
            // Сусідні сегменти неминуче торкаються біля суглобів — глушимо
            // пари з відстанню в ієрархії ≤ 2 рівні.
            for (int i = 0; i < all.Length; i++)
                for (int j = i + 1; j < all.Length; j++)
                    if (HierarchyDistance(all[i].transform, all[j].transform) <= 2)
                        Physics.IgnoreCollision(all[i], all[j], true);
        }

        private static int HierarchyDistance(Transform a, Transform b)
        {
            int d = 0;
            var pa = a; var pb = b;
            var chain = new HashSet<Transform>();
            while (pa != null) { chain.Add(pa); pa = pa.parent; }
            while (pb != null && !chain.Contains(pb)) { d++; pb = pb.parent; }
            return pb == null ? int.MaxValue : d;
        }
    }

    /// <summary>Ретранслятор колізій сегмента до площадки.</summary>
    public class LinkCollisionReporter : MonoBehaviour
    {
        public delegate void Handler(Collision c);
        public Handler OnHit;
        private void OnCollisionEnter(Collision c) => OnHit?.Invoke(c);
    }
}
