-- Ежемесячный отчёт по клубу (v1)
-- Параметры: :club_id, :start, :end

SELECT
    (SELECT SUM(amount_kop) FROM sales
      WHERE club_id = :club_id AND sale_date >= :start AND sale_date < :end) AS revenue_kop,

    (SELECT COUNT(*) FROM visits
      WHERE club_id = :club_id AND visit_date >= :start AND visit_date < :end) AS visits,

    ROUND(
        1.0 * (SELECT COUNT(*) FROM sales
                WHERE club_id = :club_id AND kind = 'membership'
                  AND sale_date >= :start AND sale_date < :end)
        / NULLIF((SELECT COUNT(*) FROM visits
                   WHERE club_id = :club_id AND visit_type = 'trial'
                     AND visit_date >= :start AND visit_date < :end), 0),
        3
    ) AS trial_conversion;
