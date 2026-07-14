// GenomeSpec.cs — константи GENOME_SPEC.md v1.0 і декодер генома.
// Єдине місце, де нормовані гени [-1,1] перетворюються на фізику.
using System.Collections.Generic;
using UnityEngine;

namespace GAExperiment
{
    public static class GenomeSpec
    {
        public const int Links = 6;
        public const int Phases = 4;
        public const int ConstructionGenes = 18;   // a[6] + alpha[6] + d[6]
        public const int MotionGenes = 24;         // 4 фази × 6 суглобів

        // Діапазони конструкції (§1)
        public const float AMin = 0f,    AMax = 0.35f;   // м
        public const float AlphaMin = -90f, AlphaMax = 90f; // °
        public const float DMin = 0f,    DMax = 0.30f;   // м

        // Ліміти суглобів і фази (§2)
        public const float JointLimitDeg = 150f;
        public static readonly float[] PhaseDurations = { 2.0f, 2.5f, 2.5f, 2.0f };

        // Константи середовища (§3) — локальні координати площадки
        public static readonly Vector3 PartPickupPos = new Vector3(-0.45f, 0.20f, 0f);
        public static readonly Vector3 MountPos      = new Vector3( 0.50f, 0.25f, 0.10f);
        public const float SuccessTolerance = 0.005f;   // м (фінальний, v1.0)
        /// <summary>Поточний допуск (curriculum): сервер стискає 50→5 мм.</summary>
        public static float CurrentSuccessTolerance = SuccessTolerance;
        public const float GraspDistance    = 0.010f;   // м (фінальний, v1.0)
        /// <summary>Поточний радіус захоплення (curriculum): 2×допуск, 80→10 мм.</summary>
        public static float CurrentGraspRadius = GraspDistance;
        public const float PartMass         = 0.15f;    // кг
        public const float LinkDensity      = 2.0f;     // кг/м
        public const float LinkMinMass      = 0.3f;     // кг
        public const float LinkRadius       = 0.025f;   // м
        public const float ToolLength       = 0.08f;    // м, ефектор уздовж x
        public const float PlatformTimeLimit = 30f;     // с, страховка
        public const float SettleAfterCycle  = 3f;      // с після фази 4

        // Драйв суглобів (константи середовища, не еволюціонують)
        public const float DriveStiffness = 2000f;
        public const float DriveDamping   = 100f;
        public const float DriveForceLimit = 300f;

        public static float Unpack(float g, float min, float max)
            => min + (Mathf.Clamp(g, -1f, 1f) + 1f) * 0.5f * (max - min);
    }

    /// <summary>Розгорнутий геном: фізичні параметри руки і рухів.</summary>
    public class DecodedGenome
    {
        public float[] A     = new float[GenomeSpec.Links];      // м
        public float[] Alpha = new float[GenomeSpec.Links];      // °
        public float[] D     = new float[GenomeSpec.Links];      // м
        // [фаза, суглоб] → цільовий кут, °
        public float[,] PhaseTargets = new float[GenomeSpec.Phases, GenomeSpec.Links];

        public static DecodedGenome Decode(Genome g)
        {
            var dg = new DecodedGenome();
            List<float> c = g.Construction, m = g.Motion;
            for (int i = 0; i < GenomeSpec.Links; i++)
            {
                dg.A[i]     = GenomeSpec.Unpack(c[i],      GenomeSpec.AMin, GenomeSpec.AMax);
                dg.Alpha[i] = GenomeSpec.Unpack(c[6 + i],  GenomeSpec.AlphaMin, GenomeSpec.AlphaMax);
                dg.D[i]     = GenomeSpec.Unpack(c[12 + i], GenomeSpec.DMin, GenomeSpec.DMax);
            }
            for (int j = 0; j < GenomeSpec.Phases; j++)
                for (int i = 0; i < GenomeSpec.Links; i++)
                    dg.PhaseTargets[j, i] = GenomeSpec.Unpack(
                        m[j * GenomeSpec.Links + i],
                        -GenomeSpec.JointLimitDeg, GenomeSpec.JointLimitDeg);
            return dg;
        }
    }
}
