// ExperimentOrchestrator.cs — спавнить сітку площадок і виконує оцінку
// покоління: роздає геноми, чекає завершення всіх, збирає результати.
// Підключається до GAExperimentClient через делегат RunSimulation.
//
// Використання: на той самий GameObject, де висить GAExperimentClient,
// додати цей компонент. Він сам перехопить RunSimulation в Awake.
using System;
using System.Collections;
using System.Collections.Generic;
using UnityEngine;

namespace GAExperiment
{
    [RequireComponent(typeof(GAExperimentClient))]
    public class ExperimentOrchestrator : MonoBehaviour
    {
        [Header("Площадки")]
        [SerializeField] private int platformCount = 100;
        [SerializeField] private int gridColumns = 10;
        [SerializeField] private float spacing = 8f;

        [Header("Час")]
        [Tooltip("Прискорення симуляції. Реальний виграш обмежений CPU.")]
        [SerializeField] private float timeScale = 1f;

        [Header("Візуал")]
        [Tooltip("URP-матеріал для всіх рантайм-об'єктів. Обов'язково для білда: без посилання з інспектора URP виріже шейдер і все стане рожевим.")]
        [SerializeField] private Material objectMaterial;
        public static Material SharedMaterial { get; set; }

        // Палітра типів об'єктів — однакова для всіх особин
        public static readonly Color ArmColor   = new Color(0.75f, 0.78f, 0.85f); // сталевий
        public static readonly Color ToolColor  = new Color(0.25f, 0.28f, 0.33f); // темний
        public static readonly Color PartColor  = new Color(0.90f, 0.30f, 0.20f); // червона деталь
        public static readonly Color FloorColor = new Color(0.55f, 0.55f, 0.52f); // площадка
        public static readonly Color StandColor = new Color(0.20f, 0.60f, 0.55f); // підставка
        public static readonly Color MountColor = new Color(0.95f, 0.75f, 0.20f); // точка монтажу

        private static MaterialPropertyBlock _mpb;

        /// <summary>Призначає спільний матеріал і колір без створення інстансів.</summary>
        public static void Paint(GameObject go, Color c)
        {
            var r = go.GetComponent<MeshRenderer>();
            if (r == null) return;
            if (SharedMaterial != null) r.sharedMaterial = SharedMaterial;
            _mpb ??= new MaterialPropertyBlock();
            _mpb.Clear();
            _mpb.SetColor("_BaseColor", c); // URP Lit
            _mpb.SetColor("_Color", c);     // сумісність зі Standard в редакторі
            r.SetPropertyBlock(_mpb);
        }

        private readonly List<AssemblyPlatform> _platforms = new();

        private void Awake()
        {
            Application.runInBackground = true;
            SharedMaterial = objectMaterial;
            Time.timeScale = timeScale;
            // При timeScale > 1 Unity має встигати робити більше фізичних
            // кроків за кадр — інакше симуляція "гальмує", а не прискорюється
            Time.maximumDeltaTime = Mathf.Max(0.333f, 0.02f * timeScale * 2f);

            for (int i = 0; i < platformCount; i++)
            {
                var go = new GameObject($"Platform_{i:D3}");
                go.transform.SetParent(transform, false);
                go.transform.localPosition = new Vector3(
                    (i % gridColumns) * spacing, 0f,
                    (i / gridColumns) * spacing);
                var p = go.AddComponent<AssemblyPlatform>();
                p.Init();
                _platforms.Add(p);
            }

            GetComponent<GAExperimentClient>().RunSimulation = RunGeneration;
        }

        /// <summary>Оцінка покоління: батчами по platformCount.</summary>
        private IEnumerator RunGeneration(List<Genome> genomes,
                                          Action<List<IndividualResult>> done)
        {
            var results = new List<IndividualResult>(genomes.Count);

            for (int offset = 0; offset < genomes.Count; offset += _platforms.Count)
            {
                int batch = Mathf.Min(_platforms.Count, genomes.Count - offset);

                for (int k = 0; k < batch; k++)
                    _platforms[k].Run(genomes[offset + k]);

                // Чекаємо завершення всіх площадок батча
                bool allDone = false;
                while (!allDone)
                {
                    yield return new WaitForFixedUpdate();
                    allDone = true;
                    for (int k = 0; k < batch; k++)
                        if (!_platforms[k].Finished) { allDone = false; break; }
                }

                for (int k = 0; k < batch; k++)
                {
                    results.Add(_platforms[k].Result);
                    _platforms[k].Cleanup(); // звільняємо руку/деталь одразу
                }
            }

            done(results);
        }
    }
}
