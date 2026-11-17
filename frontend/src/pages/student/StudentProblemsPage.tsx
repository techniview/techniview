import { useEffect, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { getCurriculum, type CurriculumPool } from "../../api/curriculum";
import {
    getAvailableProblems,
    type ProblemListResponse,
    type ProblemSummary,
} from "../../api/problems";
import ErrorState from "../../components/ErrorState";
import LoadingState from "../../components/LoadingState";

const PAGE_SIZE = 25;

function formatDifficulty(difficulty: ProblemSummary["difficulty"]): string {
    return difficulty.charAt(0).toUpperCase() + difficulty.slice(1);
}

export default function StudentProblemsPage() {
    const [searchParams, setSearchParams] = useSearchParams();
    const requestedPage = Number(searchParams.get("page") ?? "1");
    const page =
        Number.isSafeInteger(requestedPage) && requestedPage > 0 ? requestedPage : 1;
    const search = searchParams.get("search") ?? "";
    const difficulty = searchParams.get("difficulty") ?? "";
    const tag = searchParams.get("tag") ?? "";
    const sortOption = searchParams.get("sort");
    const sort =
        sortOption === "title" ||
        sortOption === "title_desc" ||
        sortOption === "difficulty_asc" ||
        sortOption === "difficulty_desc"
            ? sortOption
            : "trail";
    const [searchInput, setSearchInput] = useState(search);
    const [result, setResult] = useState<ProblemListResponse | null>(null);
    const [techniques, setTechniques] = useState<CurriculumPool[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => setSearchInput(search), [search]);

    useEffect(() => {
        let isCurrent = true;
        void getCurriculum()
            .then((items) => {
                if (isCurrent) setTechniques(items);
            })
            .catch(() => {
                // Search and difficulty remain available if the Trail request fails.
            });
        return () => {
            isCurrent = false;
        };
    }, []);

    useEffect(() => {
        let isCurrent = true;
        setIsLoading(true);

        async function loadProblems() {
            try {
                const response = await getAvailableProblems(
                    (page - 1) * PAGE_SIZE,
                    PAGE_SIZE,
                    { search, difficulty, tag, sort },
                );
                if (!isCurrent) return;
                const lastPage = Math.max(1, Math.ceil(response.total / PAGE_SIZE));
                if (page > lastPage) {
                    const next = new URLSearchParams(searchParams);
                    if (lastPage === 1) next.delete("page");
                    else next.set("page", String(lastPage));
                    setSearchParams(next, { replace: true });
                    return;
                }
                setResult(response);
                setError(null);
            } catch {
                if (isCurrent) setError("We could not load the available problems.");
            } finally {
                if (isCurrent) setIsLoading(false);
            }
        }

        void loadProblems();
        return () => {
            isCurrent = false;
        };
    }, [page, search, difficulty, tag, sort, searchParams, setSearchParams]);

    function updateFilter(key: string, value: string) {
        const next = new URLSearchParams(searchParams);
        if (value) next.set(key, value);
        else next.delete(key);
        next.delete("page");
        setSearchParams(next);
    }

    function submitSearch(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        updateFilter("search", searchInput.trim());
    }

    function goToPage(nextPage: number) {
        const next = new URLSearchParams(searchParams);
        if (nextPage === 1) next.delete("page");
        else next.set("page", String(nextPage));
        setSearchParams(next);
    }

    if (isLoading && result === null) {
        return <LoadingState message="Loading available problems..." />;
    }
    if (error) return <ErrorState message={error} />;

    return (
        <div className="student-problems-page">
            <header className="page-header">
                <h1>All Problems</h1>
                <p>
                    Explore the Trail first, then keep practicing with the full catalog.
                </p>
            </header>

            <div className="problem-toolbar">
                <form className="problem-search" onSubmit={submitSearch} role="search">
                    <label htmlFor="problem-search">Search problems</label>
                    <div>
                        <input
                            id="problem-search"
                            onChange={(event) => setSearchInput(event.target.value)}
                            placeholder="Search by title"
                            type="search"
                            value={searchInput}
                        />
                        <button type="submit">Search</button>
                    </div>
                </form>
                <label>
                    Difficulty
                    <select
                        onChange={(event) =>
                            updateFilter("difficulty", event.target.value)
                        }
                        value={difficulty}
                    >
                        <option value="">All difficulties</option>
                        <option value="easy">Easy</option>
                        <option value="medium">Medium</option>
                        <option value="hard">Hard</option>
                    </select>
                </label>
                <label>
                    Technique
                    <select
                        onChange={(event) => updateFilter("tag", event.target.value)}
                        value={tag}
                    >
                        <option value="">All techniques</option>
                        {techniques.map((pool) => (
                            <option key={pool.slug} value={pool.slug}>
                                {pool.name}
                            </option>
                        ))}
                    </select>
                </label>
                <label>
                    Sort
                    <select
                        onChange={(event) => updateFilter("sort", event.target.value)}
                        value={sort}
                    >
                        <option value="trail">Trail first</option>
                        <option value="title">Title A-Z</option>
                        <option value="title_desc">Title Z-A</option>
                        <option value="difficulty_asc">Easy to hard</option>
                        <option value="difficulty_desc">Hard to easy</option>
                    </select>
                </label>
            </div>

            <p className="problem-count" aria-live="polite">
                {result?.total ?? 0} problems
                {result &&
                    result.total > 0 &&
                    ` · Showing ${result.offset + 1}-${result.offset + result.items.length}`}
            </p>

            <div className="table-wrapper">
                <table aria-label="Available problems">
                    <thead>
                        <tr>
                            <th className="problem-rank" scope="col">
                                #
                            </th>
                            <th scope="col">Problem</th>
                            <th className="difficulty-column" scope="col">
                                Difficulty
                            </th>
                            <th scope="col">Type</th>
                        </tr>
                    </thead>
                    <tbody>
                        {result?.items.map((problem, index) => {
                            const problemType =
                                problem.typed_tags
                                    .find((item) => item.kind === "problem_type")
                                    ?.name.replace(/\s*\(Problem Type\)$/, "") ??
                                "General";
                            const assignmentItemId =
                                problem.available_assignment_item_id;
                            return (
                                <tr key={problem.id}>
                                    <td className="problem-rank">
                                        {result.offset + index + 1}
                                    </td>
                                    <th scope="row">
                                        <Link
                                            to={`/student/problems/${problem.id}${assignmentItemId === null ? "" : `?assignment_item_id=${assignmentItemId}`}`}
                                        >
                                            {problem.title}
                                        </Link>
                                    </th>
                                    <td className="difficulty-column">
                                        <span
                                            className={`difficulty-pill difficulty-${problem.difficulty}`}
                                        >
                                            {formatDifficulty(problem.difficulty)}
                                        </span>
                                    </td>
                                    <td>{problemType}</td>
                                </tr>
                            );
                        })}
                        {result?.items.length === 0 && (
                            <tr>
                                <td colSpan={4}>No problems match these filters.</td>
                            </tr>
                        )}
                    </tbody>
                </table>
            </div>
            {result && result.total > PAGE_SIZE && (
                <nav className="problem-pagination" aria-label="Problem pages">
                    <button
                        disabled={page === 1 || isLoading}
                        onClick={() => goToPage(page - 1)}
                        type="button"
                    >
                        Previous
                    </button>
                    <span>
                        Page {page} of {Math.ceil(result.total / PAGE_SIZE)}
                    </span>
                    <button
                        disabled={
                            page >= Math.ceil(result.total / PAGE_SIZE) || isLoading
                        }
                        onClick={() => goToPage(page + 1)}
                        type="button"
                    >
                        Next
                    </button>
                </nav>
            )}
        </div>
    );
}
