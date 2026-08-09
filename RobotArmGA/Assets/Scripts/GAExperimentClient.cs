// GAExperimentClient.cs
// Клієнт циклу GA-експерименту: отримує геноми покоління, віддає їх
// симуляції (спавн площадок з роботами), збирає fitness і надсилає назад.
//
// Залежності: Newtonsoft Json.NET — Package Manager → Add by name →
//             com.unity.nuget.newtonsoft-json
// Ніяких UNet/Netcode не потрібно: тільки UnityWebRequest (живий і актуальний).

using System;
using System.Collections;
using System.Collections.Generic;
using System.Text;
using Newtonsoft.Json;
using UnityEngine;
using UnityEngine.Networking; // тут живе UnityWebRequest — це НЕ UNet

namespace GAExperiment
{
    // ── DTO: дзеркало protocol.py ────────────────────────────────────────
    [Serializable]
    public class Genome
    {
        [JsonProperty("individual_id")] public int IndividualId;
        [JsonProperty("construction")]  public List<float> Construction;
        [JsonProperty("motion")]        public List<float> Motion;
    }

    [Serializable]
    public class Generation
    {
        [JsonProperty("generation_id")]     public int GenerationId;
        [JsonProperty("genomes")]           public List<Genome> Genomes;
        [JsonProperty("done")]              public bool Done;
        [JsonProperty("best_fitness")]      public float? BestFitness;
        [JsonProperty("success_tolerance")] public float SuccessTolerance = 0.005f;
    }

    [Serializable]
    public class IndividualResult
    {
        [JsonProperty("individual_id")]    public int IndividualId;
        [JsonProperty("fitness")]          public float Fitness; // рахує сервер
        [JsonProperty("assembly_time")]    public float AssemblyTime;
        [JsonProperty("energy")]           public float Energy;
        [JsonProperty("wear_cv")]          public float WearCv;
        [JsonProperty("wear_max")]         public float WearMax;
        [JsonProperty("joint_work")]       public List<float> JointWork = new();
        [JsonProperty("precision_error")]  public float PrecisionError;
        [JsonProperty("collisions")]       public int Collisions;
        [JsonProperty("success")]          public bool Success;
        // Діагностичне (не впливає на fitness/відбір) — реальний шлях
        // деталі / пряма, див. protocol.py IndividualResult.
        [JsonProperty("path_efficiency")]  public float PathEfficiency;
    }

    [Serializable]
    public class GenerationResults
    {
        [JsonProperty("generation_id")] public int GenerationId;
        [JsonProperty("results")]       public List<IndividualResult> Results;
    }

    [Serializable]
    public class ExperimentConfig
    {
        [JsonProperty("population_size")]         public int PopulationSize = 50;
        [JsonProperty("construction_gene_count")] public int ConstructionGeneCount = 8;
        [JsonProperty("motion_gene_count")]       public int MotionGeneCount = 24;
        [JsonProperty("max_generations")]         public int MaxGenerations = 100;
        // FIX (сесія 2026-08): було "int? Seed" — Unity Inspector НЕ вміє
        // серіалізувати Nullable<T> для звичайних класів і мовчки ховає
        // таке поле зі списку (без помилок!). Поле було невидиме й
        // незмінне через UI відколи його додали — усі прогони йшли на
        // застиглому дефолті 42, попри намір варіювати сід між серіями.
        [JsonProperty("seed")]                    public int Seed = 42; // відтворюваність!
        // Автоматизація FIGURE_MANIFEST: заповни для офіційної серії
        // (напр. "fig5-curriculum"), лиши порожнім для технічних тестів.
        [JsonProperty("series_label")]            public string SeriesLabel = "";
        // Т3/Т10: "self_paced" (тригер Шмітта) або "open_loop" (сліпий
        // розклад, відтворення Серії A для Рис.4 A vs B).
        [JsonProperty("curriculum_strategy")]     public string CurriculumStrategy = "self_paced";
        // ПРИМІТКА: mutation_strategy / curriculum_gate_tighten /
        // curriculum_gate_loosen / optimizer поки НЕ дзеркалені тут —
        // Unity їх не надсилає, сервер підставляє свої дефолти
        // (nsga2, p_control, 0.25/0.02). Додати за потреби для серії Т10
        // чи порівняння weighted_sum/nsga2 з інспектора.
    }

    // ── Клієнт ───────────────────────────────────────────────────────────
    public class GAExperimentClient : MonoBehaviour
    {
        [Header("Сервер")]
        [SerializeField] private string serverUrl = "http://127.0.0.1:8000";
        [Tooltip("Таймаут відповіді, с. Врахуй час роботи GA на великих популяціях.")]
        [SerializeField] private int requestTimeout = 120;

        [Header("Експеримент")]
        [SerializeField] private ExperimentConfig config = new ExperimentConfig();

        /// <summary>
        /// Сюди підключається симуляція: отримує геноми, спавнить площадки,
        /// проводить монтаж деталі, викликає onComplete з результатами.
        /// </summary>
        public Func<List<Genome>, Action<List<IndividualResult>>, IEnumerator>
            RunSimulation;

        public event Action<Generation> OnGenerationReceived;
        public event Action<int, float?> OnExperimentFinished; // (поколінь, best)

        // ── HUD (прохання Сергія: бачити стан прогону на екрані) ─────────
        private int _hudGen;
        private float _hudTol, _hudBest;
        private int _hudSuccess = -1, _hudPop;
        private GUIStyle _hudStyle;

        private void OnGUI()
        {
            _hudStyle ??= new GUIStyle(GUI.skin.label)
            { fontSize = 20, richText = true };
            string succ = _hudSuccess < 0 ? "—"
                : $"{_hudSuccess}/{_hudPop} ({100f * _hudSuccess / Mathf.Max(1, _hudPop):F1}%)";
            GUI.Label(new Rect(12, 8, 700, 130),
                $"<b>Покоління:</b> {_hudGen}\n" +
                $"<b>Допуск:</b> {_hudTol * 1000f:F1} мм   " +
                $"<b>Радіус захвату:</b> {GenomeSpec.CurrentGraspRadius * 1000f:F0} мм\n" +
                $"<b>Best fitness:</b> {_hudBest:F3}   " +
                $"<b>Успіхи минулого покоління:</b> {succ}", _hudStyle);
        }

        private void Start()
        {
            if (RunSimulation == null)
                RunSimulation = RunSimulationStub; // заглушка, поки немає сцени
            StartCoroutine(ExperimentLoop());
        }

        // ── Головний цикл ────────────────────────────────────────────────
        private IEnumerator ExperimentLoop()
        {
            Generation gen = null;

            yield return Post("/experiment/start", config,
                              (Generation g) => gen = g);
            if (gen == null) yield break; // помилка вже в консолі

            while (true)
            {
                OnGenerationReceived?.Invoke(gen);
                GenomeSpec.CurrentSuccessTolerance = gen.SuccessTolerance; // curriculum
                GenomeSpec.CurrentGraspRadius = Mathf.Clamp(
                    2f * gen.SuccessTolerance, 0.010f, 0.080f);            // ворота захвату
                _hudGen = gen.GenerationId;
                _hudTol = gen.SuccessTolerance;
                _hudBest = gen.BestFitness ?? 0f;
                Debug.Log($"[GA] Покоління {gen.GenerationId}: " +
                          $"{gen.Genomes.Count} особин, best={gen.BestFitness}, " +
                          $"допуск={gen.SuccessTolerance * 1000f:F0} мм");

                if (gen.Done)
                {
                    Debug.Log($"[GA] Готово. Найкращий fitness: {gen.BestFitness}");
                    OnExperimentFinished?.Invoke(gen.GenerationId, gen.BestFitness);
                    yield break;
                }

                // 1. Експеримент у симуляції
                List<IndividualResult> results = null;
                yield return RunSimulation(gen.Genomes, r => results = r);

                // 2. Результати → сервер, відповідь = наступне покоління
                _hudSuccess = 0; _hudPop = results.Count;
                foreach (var r in results) if (r.Success) _hudSuccess++;
                var payload = new GenerationResults
                {
                    GenerationId = gen.GenerationId,
                    Results = results
                };
                Generation next = null;
                yield return Post("/experiment/results", payload,
                                  (Generation g) => next = g);
                if (next == null) yield break;
                gen = next;
            }
        }

        // ── HTTP ─────────────────────────────────────────────────────────
        private IEnumerator Post<TRes>(string path, object body, Action<TRes> onOk)
        {
            string json = JsonConvert.SerializeObject(body);
            using var req = new UnityWebRequest(serverUrl + path, "POST");
            req.uploadHandler = new UploadHandlerRaw(Encoding.UTF8.GetBytes(json));
            req.downloadHandler = new DownloadHandlerBuffer();
            req.SetRequestHeader("Content-Type", "application/json");
            req.timeout = requestTimeout;

            yield return req.SendWebRequest();

            if (req.result != UnityWebRequest.Result.Success)
            {
                Debug.LogError($"[GA] {path}: {req.error}\n{req.downloadHandler.text}");
                yield break;
            }
            onOk(JsonConvert.DeserializeObject<TRes>(req.downloadHandler.text));
        }

        // ── Заглушка симуляції ───────────────────────────────────────────
        // Дає перевірити зв'язок ще ДО того, як готова сцена з роботами:
        // fitness рахується як фіктивна функція генів.
        private IEnumerator RunSimulationStub(List<Genome> genomes,
                                              Action<List<IndividualResult>> done)
        {
            yield return new WaitForSeconds(0.1f); // імітація тривалості
            var results = new List<IndividualResult>();
            foreach (var g in genomes)
            {
                float f = 0f;
                foreach (var x in g.Construction) f -= (x - 0.6f) * (x - 0.6f);
                foreach (var x in g.Motion)       f -= 0.1f * x * x;
                results.Add(new IndividualResult
                {
                    IndividualId = g.IndividualId,
                    Fitness = f,
                    AssemblyTime = UnityEngine.Random.Range(20f, 60f),
                    Success = true
                });
            }
            done(results);
        }
    }
}
