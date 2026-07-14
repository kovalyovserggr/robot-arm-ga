// ChampionReplay.cs — оглядини чемпіона: тягне найкращий геном прогону
// з сервера (GET /experiment/champion) і крутить його на одній площадці
// по колу. Для розглядання конструкції, зйомки кадрів у статтю і
// перевірки відтворюваності успіху.
//
// Використання: ПОРОЖНЯ сцена (або вимкни об'єкт з GAExperimentClient/
// ExperimentOrchestrator) -> Empty GameObject -> цей компонент ->
// признач Object Material. Сервер має бути запущений, прогін — завершений
// або живий (чемпіон оновлюється по ходу).
using System.Collections;
using Newtonsoft.Json;
using UnityEngine;
using UnityEngine.Networking;

namespace GAExperiment
{
    public class ChampionReplay : MonoBehaviour
    {
        [SerializeField] private string serverUrl = "http://127.0.0.1:8000";
        [SerializeField] private Material objectMaterial;
        [SerializeField] private float pauseBetweenRuns = 1.5f;
        [Tooltip("Перезапитувати чемпіона перед кожним повтором (для живого прогону)")]
        [SerializeField] private bool refreshEachRun = false;

        private AssemblyPlatform _platform;
        private ChampionDto _champ;
        private string _lastResult = "";
        private GUIStyle _style;

        private class ChampionDto
        {
            [JsonProperty("generation")] public int Generation;
            [JsonProperty("fitness")]    public float Fitness;
            [JsonProperty("tolerance")]  public float Tolerance;
            [JsonProperty("genome")]     public Genome Genome;
        }

        private void Start()
        {
            Application.runInBackground = true;
            ExperimentOrchestrator.SharedMaterial = objectMaterial;

            var go = new GameObject("ChampionPlatform");
            go.transform.SetParent(transform, false);
            _platform = go.AddComponent<AssemblyPlatform>();
            _platform.Init();

            StartCoroutine(Loop());
        }

        private IEnumerator Loop()
        {
            yield return Fetch();
            if (_champ == null) yield break;

            while (true)
            {
                if (refreshEachRun) yield return Fetch();

                GenomeSpec.CurrentSuccessTolerance = Mathf.Max(0.005f, _champ.Tolerance);
                GenomeSpec.CurrentGraspRadius =
                    Mathf.Clamp(2f * _champ.Tolerance, 0.010f, 0.080f);

                _platform.Run(_champ.Genome);
                while (!_platform.Finished) yield return new WaitForFixedUpdate();

                var r = _platform.Result;
                _lastResult = $"success={r.Success}  похибка={r.PrecisionError * 1000f:F1} мм  " +
                              $"E={r.Energy:F0} Дж  W_cv={r.WearCv:F2}  T={r.AssemblyTime:F1} с";
                Debug.Log($"[Champion] {_lastResult}");
                yield return new WaitForSeconds(pauseBetweenRuns);
            }
        }

        private IEnumerator Fetch()
        {
            using var req = UnityWebRequest.Get(serverUrl + "/experiment/champion");
            req.timeout = 15;
            yield return req.SendWebRequest();
            if (req.result != UnityWebRequest.Result.Success)
            {
                Debug.LogError($"[Champion] {req.error} — сервер запущений? " +
                               $"Прогін був? {req.downloadHandler.text}");
                yield break;
            }
            _champ = JsonConvert.DeserializeObject<ChampionDto>(req.downloadHandler.text);
        }

        private void OnGUI()
        {
            if (_champ == null) return;
            _style ??= new GUIStyle(GUI.skin.label) { fontSize = 20, richText = true };
            GUI.Label(new Rect(12, 8, 900, 90),
                $"<b>Чемпіон</b>: покоління {_champ.Generation}, " +
                $"fitness {_champ.Fitness:F3}, допуск {_champ.Tolerance * 1000f:F0} мм\n" +
                $"<b>Останній прогін:</b> {_lastResult}", _style);
        }
    }
}
