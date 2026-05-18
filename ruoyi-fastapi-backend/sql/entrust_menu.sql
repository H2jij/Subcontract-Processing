-- =====================================================
-- 委外管理模块菜单 SQL（sys_menu）
-- 需要在 PostgreSQL 的 weiwai 数据库中执行
-- =====================================================

-- 重置序列到安全值（避免冲突）
SELECT setval('sys_menu_menu_id_seq', 9500, false);

-- =====================================================
-- 一级目录：委外管理
-- =====================================================
INSERT INTO "public"."sys_menu" VALUES (
    9400, '委外管理', 0, 5, 'entrust', NULL, '', '', 1, 0, 'M', '0', '0', '', 'shopping', 'admin', now(), '', NULL, '委外管理目录'
);

-- =====================================================
-- 二级菜单：项目管理
-- =====================================================
INSERT INTO "public"."sys_menu" VALUES (
    9401, '项目管理', 9400, 1, 'project', 'entrust/project/index', '', '', 1, 0, 'C', '0', '0', 'entrust:project:list', 'documentation', 'admin', now(), '', NULL, '项目管理菜单'
);
-- 项目管理按钮
INSERT INTO "public"."sys_menu" VALUES (9402, '项目查询', 9401, 1, '#', '', '', '', 1, 0, 'F', '0', '0', 'entrust:project:query', '#', 'admin', now(), '', NULL, '');
INSERT INTO "public"."sys_menu" VALUES (9403, '项目新增', 9401, 2, '#', '', '', '', 1, 0, 'F', '0', '0', 'entrust:project:add', '#', 'admin', now(), '', NULL, '');
INSERT INTO "public"."sys_menu" VALUES (9404, '项目修改', 9401, 3, '#', '', '', '', 1, 0, 'F', '0', '0', 'entrust:project:edit', '#', 'admin', now(), '', NULL, '');
INSERT INTO "public"."sys_menu" VALUES (9405, '项目删除', 9401, 4, '#', '', '', '', 1, 0, 'F', '0', '0', 'entrust:project:remove', '#', 'admin', now(), '', NULL, '');

-- =====================================================
-- 二级菜单：加工方管理
-- =====================================================
INSERT INTO "public"."sys_menu" VALUES (
    9410, '加工方管理', 9400, 2, 'supplier', 'entrust/supplier/index', '', '', 1, 0, 'C', '0', '0', 'entrust:supplier:list', 'peoples', 'admin', now(), '', NULL, '加工方管理菜单'
);
-- 加工方管理按钮
INSERT INTO "public"."sys_menu" VALUES (9411, '加工方查询', 9410, 1, '#', '', '', '', 1, 0, 'F', '0', '0', 'entrust:supplier:query', '#', 'admin', now(), '', NULL, '');
INSERT INTO "public"."sys_menu" VALUES (9412, '加工方新增', 9410, 2, '#', '', '', '', 1, 0, 'F', '0', '0', 'entrust:supplier:add', '#', 'admin', now(), '', NULL, '');
INSERT INTO "public"."sys_menu" VALUES (9413, '加工方修改', 9410, 3, '#', '', '', '', 1, 0, 'F', '0', '0', 'entrust:supplier:edit', '#', 'admin', now(), '', NULL, '');
INSERT INTO "public"."sys_menu" VALUES (9414, '加工方删除', 9410, 4, '#', '', '', '', 1, 0, 'F', '0', '0', 'entrust:supplier:remove', '#', 'admin', now(), '', NULL, '');

-- =====================================================
-- 二级菜单：询价管理
-- =====================================================
INSERT INTO "public"."sys_menu" VALUES (
    9420, '询价管理', 9400, 3, 'inquiry', 'entrust/inquiry/index', '', '', 1, 0, 'C', '0', '0', 'entrust:inquiry:list', 'form', 'admin', now(), '', NULL, '询价管理菜单'
);
-- 询价管理按钮
INSERT INTO "public"."sys_menu" VALUES (9421, '询价查询', 9420, 1, '#', '', '', '', 1, 0, 'F', '0', '0', 'entrust:inquiry:query', '#', 'admin', now(), '', NULL, '');
INSERT INTO "public"."sys_menu" VALUES (9422, '询价新增', 9420, 2, '#', '', '', '', 1, 0, 'F', '0', '0', 'entrust:inquiry:add', '#', 'admin', now(), '', NULL, '');
INSERT INTO "public"."sys_menu" VALUES (9423, '询价修改', 9420, 3, '#', '', '', '', 1, 0, 'F', '0', '0', 'entrust:inquiry:edit', '#', 'admin', now(), '', NULL, '');
INSERT INTO "public"."sys_menu" VALUES (9424, '询价删除', 9420, 4, '#', '', '', '', 1, 0, 'F', '0', '0', 'entrust:inquiry:remove', '#', 'admin', now(), '', NULL, '');
INSERT INTO "public"."sys_menu" VALUES (9425, '询价发送', 9420, 5, '#', '', '', '', 1, 0, 'F', '0', '0', 'entrust:inquiry:send', '#', 'admin', now(), '', NULL, '');
INSERT INTO "public"."sys_menu" VALUES (9426, '选标', 9420, 6, '#', '', '', '', 1, 0, 'F', '0', '0', 'entrust:inquiry:award', '#', 'admin', now(), '', NULL, '');

-- =====================================================
-- 将委外管理菜单分配给 admin 角色（role_id=1）
-- =====================================================
INSERT INTO "public"."sys_role_menu" (role_id, menu_id) VALUES
    (1, 9400),
    (1, 9401), (1, 9402), (1, 9403), (1, 9404), (1, 9405),
    (1, 9410), (1, 9411), (1, 9412), (1, 9413), (1, 9414),
    (1, 9420), (1, 9421), (1, 9422), (1, 9423), (1, 9424), (1, 9425), (1, 9426);
