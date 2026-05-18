-- Insert 4 roles
INSERT INTO "public"."sys_role" (role_id, role_name, role_key, role_sort, data_scope, menu_check_strictly, dept_check_strictly, status, del_flag, create_by, create_time, remark) VALUES
(100, '系统管理员', 'our_admin', 1, '1', 1, 1, '0', '0', 'admin', now(), '系统管理员'),
(101, '经理', 'manager', 2, '1', 1, 1, '0', '0', 'admin', now(), '审批项目，查看所有业务'),
(102, '业务员', 'buyer', 3, '1', 1, 1, '0', '0', 'admin', now(), '创建项目，提交审批，管理加工方'),
(103, '加工方', 'processor', 4, '5', 1, 1, '0', '0', 'admin', now(), '外部加工方');
SELECT setval('sys_role_role_id_seq', 200, false);
