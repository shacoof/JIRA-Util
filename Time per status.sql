select FROM_STATUS,TO_STATUS,round(avg(hours_in_status)), count(*)
from Q2V2ALL_HISTORY
where CHANGED_FIELD = 'status'
group by FROM_STATUS,TO_STATUS
having count(*) > 10
order by round(avg(hours_in_status)) desc